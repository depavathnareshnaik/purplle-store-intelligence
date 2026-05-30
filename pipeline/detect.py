"""
Main detection pipeline — processes CCTV clips and emits structured events.

Pipeline per clip:
  1. Load YOLOv9 and detect persons on every FRAME_STRIDE-th frame
  2. Feed detections to ByteTrack for persistent track IDs
  3. For each track: classify zone (ZoneClassifier) + staff (StaffClassifier)
  4. Feed into VisitorTracker → generates events
  5. Events buffered in EventEmitter → written to JSONL + POSTed to API

Usage (see also run.sh):
    python pipeline/detect.py --store STORE_BLR_002
    python pipeline/detect.py --store STORE_BLR_002 --api http://localhost:8000 --no-api
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("pipeline.detect")


# ---------------------------------------------------------------------------
# Clip processor
# ---------------------------------------------------------------------------

def process_clip(
    clip_path: Path,
    store_id: str,
    camera_id: str,
    camera_type: str,
    entry_threshold_y_pct: float,
    clip_start_time: datetime,
    model,
    bytetracker,
    zone_clf,
    staff_clf,
    visitor_tracker,
    emitter,
    config,
) -> int:
    """
    Process a single video clip. Returns the number of events emitted.
    """
    import cv2

    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        logger.error("Cannot open video: %s", clip_path)
        return 0

    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    entry_threshold_y = entry_threshold_y_pct * frame_h

    frame_num = 0
    event_count = 0
    last_frame_time = clip_start_time

    logger.info(
        "Processing %s  camera=%s  fps=%.1f  threshold_y=%.0f",
        clip_path.name, camera_id, fps, entry_threshold_y,
    )

    active_track_ids: set = set()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_num += 1
        if frame_num % config.frame_stride != 0:
            continue

        frame_time = clip_start_time + timedelta(seconds=frame_num / fps)
        last_frame_time = frame_time

        # ── Detection ──────────────────────────────────────────────────────
        results = model(
            frame,
            classes=[0],                        # 0 = person in COCO
            conf=config.conf_threshold,
            iou=config.iou_threshold,
            verbose=False,
        )

        import supervision as sv

        detections = sv.Detections.from_ultralytics(results[0])
        if len(detections) == 0:
            # Empty frame — handle track losses
            for tid in list(active_track_ids):
                events = visitor_tracker.on_track_lost(tid, frame_time)
                emitter.add_many(events)
                event_count += len(events)
            active_track_ids.clear()
            bytetracker = _reset_tracker(config, fps)
            continue

        # ── Tracking ───────────────────────────────────────────────────────
        tracks = bytetracker.update_with_detections(detections)
        current_ids: set = set()

        for i in range(len(tracks)):
            if tracks.tracker_id is None or tracks.tracker_id[i] is None:
                continue

            track_id = int(tracks.tracker_id[i])
            bbox = tracks.xyxy[i]
            conf = float(tracks.confidence[i]) if tracks.confidence is not None else 0.5

            current_ids.add(track_id)

            # ── Zone + staff classification ────────────────────────────────
            cx = float((bbox[0] + bbox[2]) / 2)
            cy = float((bbox[1] + bbox[3]) / 2)
            zone_id, sku_zone = zone_clf.classify(store_id, cx, cy)
            is_staff = staff_clf.is_staff(frame, bbox)

            # ── Visitor tracker → events ───────────────────────────────────
            events = visitor_tracker.update(
                track_id=track_id,
                bbox=bbox,
                frame=frame,
                zone_id=zone_id,
                sku_zone=sku_zone,
                is_staff=is_staff,
                confidence=conf,
                camera_id=camera_id,
                camera_type=camera_type,
                frame_time=frame_time,
                entry_threshold_y=entry_threshold_y,
            )
            emitter.add_many(events)
            event_count += len(events)

        # Handle tracks that disappeared this frame
        for lost_tid in active_track_ids - current_ids:
            events = visitor_tracker.on_track_lost(lost_tid, frame_time)
            emitter.add_many(events)
            event_count += len(events)

        active_track_ids = current_ids

    cap.release()

    # Flush remaining active tracks
    final_events = visitor_tracker.flush(last_frame_time)
    emitter.add_many(final_events)
    event_count += len(final_events)

    logger.info(
        "Finished %s — %d events emitted", clip_path.name, event_count
    )
    return event_count


# ---------------------------------------------------------------------------
# Store-level orchestrator
# ---------------------------------------------------------------------------

def process_store(store_id: str, config) -> None:
    """Process all clips for one store, then resolve billing abandons."""
    from ultralytics import YOLO
    import supervision as sv

    from pipeline.emit import EventEmitter, load_pos_transactions
    from pipeline.staff_classifier import StaffClassifier
    from pipeline.tracker import VisitorTracker
    from pipeline.zone_classifier import ZoneClassifier

    logger.info("=== Processing store: %s ===", store_id)

    zone_clf = ZoneClassifier.from_path(config.layout_path)
    staff_clf = StaffClassifier(config)
    visitor_tracker = VisitorTracker(config, store_id)
    emitter = EventEmitter(config, store_id)

    model = YOLO(config.model_name)

    store_clips_dir = config.clips_dir / store_id
    if not store_clips_dir.exists():
        logger.warning("No clips directory for %s at %s", store_id, store_clips_dir)
        emitter.close()
        return

    clips = sorted(store_clips_dir.glob("*.mp4")) + sorted(store_clips_dir.glob("*.avi"))
    if not clips:
        logger.warning("No video files found in %s", store_clips_dir)
        emitter.close()
        return

    logger.info("Found %d clip(s) for %s", len(clips), store_id)

    fps = 15.0  # default; overridden per-clip inside process_clip
    bytetracker = _build_tracker(config, fps)

    for clip_path in clips:
        camera_id, camera_type, threshold_y_pct = zone_clf.get_camera_info(
            store_id, clip_path.name
        )

        # Skip non-customer cameras (storage rooms etc.)
        if camera_type == "storage":
            logger.info("Skipping storage camera: %s", clip_path.name)
            continue

        clip_start = _infer_clip_start(clip_path)

        # Reset tracker per clip so ByteTrack track IDs don't leak across clips
        bytetracker = _build_tracker(config, fps)

        process_clip(
            clip_path=clip_path,
            store_id=store_id,
            camera_id=camera_id,
            camera_type=camera_type,
            entry_threshold_y_pct=threshold_y_pct,
            clip_start_time=clip_start,
            model=model,
            bytetracker=bytetracker,
            zone_clf=zone_clf,
            staff_clf=staff_clf,
            visitor_tracker=visitor_tracker,
            emitter=emitter,
            config=config,
        )

    # Post-processing: correlate billing exits with POS data
    pos_data = load_pos_transactions(config)
    abandon_events = visitor_tracker.resolve_abandons(pos_data)
    emitter.add_many(abandon_events)

    emitter.close()
    logger.info("=== Done: %s ===", store_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_tracker(config, fps: float):
    import supervision as sv

    # sv.ByteTrack is the current name (ByteTracker was renamed in supervision 0.22+)
    tracker_cls = getattr(sv, "ByteTrack", None) or getattr(sv, "ByteTracker")
    return tracker_cls(
        track_activation_threshold=config.track_activation_threshold,
        lost_track_buffer=config.lost_track_buffer,
        minimum_matching_threshold=config.minimum_matching_threshold,
        frame_rate=max(1, int(fps / config.frame_stride)),
    )


def _reset_tracker(config, fps: float):
    """Create a fresh ByteTracker — called on empty frames to prevent ghost tracks."""
    return _build_tracker(config, fps)


def _infer_clip_start(clip_path: Path) -> datetime:
    """
    Infer clip start time.

    For the Purplle Brigade Road dataset, the on-screen timestamp shows
    10/04/2026 at ~20:07–20:10 IST. We extract from ffprobe if available,
    otherwise use the known recording time for this dataset.

    IST = UTC+5:30, so 20:07 IST = 14:37 UTC on 2026-04-10.
    """
    # NOTE: ffprobe creation_time is intentionally NOT used here.
    # For the Purplle Brigade Road dataset the creation_time tag reflects the
    # clip export date (2026-04-15), not the recording date (2026-04-10).
    # The on-screen OSD timestamp is the authoritative source; the hardcoded
    # fallback at the bottom of this function matches it exactly.

    # Try filename patterns
    name = clip_path.stem
    for fmt in ("%Y%m%d_%H%M", "%Y-%m-%dT%H:%M", "%Y%m%d_%H%M%S"):
        for part in name.split("_"):
            try:
                dt = datetime.strptime(part, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

    # Known start time for Purplle Brigade Road 10-Apr-2026 footage
    # On-screen shows ~20:07 IST → 14:37 UTC
    # CAM 4/5 show 20:09 IST → 14:39 UTC
    cam_name = clip_path.name.lower()
    from datetime import timedelta
    base = datetime(2026, 4, 10, 14, 37, 0, tzinfo=timezone.utc)
    if "cam_4" in cam_name or "cam_5" in cam_name:
        base = datetime(2026, 4, 10, 14, 39, 0, tzinfo=timezone.utc)
    return base


def _discover_stores(clips_dir: Path) -> List[str]:
    """Return store IDs by listing subdirectories of clips_dir."""
    if not clips_dir.exists():
        return []
    return [d.name for d in sorted(clips_dir.iterdir()) if d.is_dir()]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Store Intelligence detection pipeline"
    )
    parser.add_argument(
        "--store", metavar="STORE_ID",
        help="Process a specific store. Omit to process all stores in data/clips/",
    )
    parser.add_argument(
        "--api", default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--no-api", action="store_true",
        help="Write JSONL only — do not POST to the API",
    )
    parser.add_argument(
        "--clips-dir", default="data/clips",
        help="Root directory of CCTV clips (default: data/clips)",
    )
    parser.add_argument(
        "--events-dir", default="data/events",
        help="Output directory for JSONL files (default: data/events)",
    )
    parser.add_argument(
        "--model", default="yolov9c.pt",
        help="YOLO model weights (default: yolov9c.pt)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    from pipeline.config import PipelineConfig

    config = PipelineConfig(
        api_url=args.api,
        ingest_to_api=not args.no_api,
        clips_dir=Path(args.clips_dir),
        events_dir=Path(args.events_dir),
        model_name=args.model,
    )

    store_ids = [args.store] if args.store else _discover_stores(config.clips_dir)

    if not store_ids:
        logger.error(
            "No stores found. Place clips in %s/<STORE_ID>/*.mp4", config.clips_dir
        )
        sys.exit(1)

    for store_id in store_ids:
        process_store(store_id, config)


if __name__ == "__main__":
    main()
