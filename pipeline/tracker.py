"""
Visitor identity tracker — the core of M1/M2.

Responsibilities:
  1. Assign stable visitor_ids to ByteTrack track_ids using OSNet Re-ID
  2. Detect ENTRY / EXIT (threshold line crossing at entry camera)
  3. Detect REENTRY (Re-ID matches a recent EXIT record)
  4. Suppress cross-camera duplicates (same person on floor + entry camera)
  5. Track zone transitions → ZONE_ENTER / ZONE_EXIT / ZONE_DWELL events
  6. Track billing queue → BILLING_QUEUE_JOIN / pending BILLING_QUEUE_ABANDON

One VisitorTracker instance is shared across all clips of the same store
so that re-entry detection works across the full recording session.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from pipeline.config import PipelineConfig

logger = logging.getLogger("pipeline.tracker")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TrackState:
    """Per-ByteTrack-ID state, lives as long as the track is active."""
    track_id: int
    visitor_id: str
    camera_id: str
    is_staff: bool
    confidence: float
    embedding: Optional[np.ndarray]

    # Zone tracking
    current_zone: Optional[str] = None
    current_sku: Optional[str] = None
    zone_entry_time: Optional[datetime] = None
    last_dwell_emit: Optional[datetime] = None

    # Entry / exit
    prev_y: Optional[float] = None
    has_entered: bool = False     # did we emit ENTRY for this visitor?

    # Billing
    in_billing: bool = False
    billing_entry_time: Optional[datetime] = None

    # Session sequence counter (increments per event)
    session_seq: int = 0

    def next_seq(self) -> int:
        self.session_seq += 1
        return self.session_seq


@dataclass
class ExitRecord:
    """Short-lived record of a visitor EXIT used for re-entry detection."""
    visitor_id: str
    embedding: np.ndarray
    exit_time: datetime
    store_id: str


@dataclass
class BillingExit:
    """Pending BILLING_QUEUE_ABANDON — resolved after POS correlation."""
    visitor_id: str
    camera_id: str
    is_staff: bool
    confidence: float
    zone_id: str
    sku_zone: Optional[str]
    dwell_ms: int
    exit_time: datetime
    session_seq: int


# ---------------------------------------------------------------------------
# Re-ID helper (OSNet with colour-histogram fallback)
# ---------------------------------------------------------------------------

class ReIDModel:
    """Thin wrapper that tries OSNet, falls back to colour histogram."""

    def __init__(self, model_name: str):
        self._model = None
        self._transforms = None
        self._use_osnet = self._try_load(model_name)

    def _try_load(self, model_name: str) -> bool:
        try:
            import torchreid
            import torch
            import torchvision.transforms as T

            self._model = torchreid.models.build_model(
                name=model_name, num_classes=1000, pretrained=True
            )
            self._model.eval()
            self._transforms = T.Compose([
                T.ToPILImage(),
                T.Resize((256, 128)),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
            logger.info("OSNet Re-ID model loaded: %s", model_name)
            return True
        except Exception as exc:
            logger.warning(
                "torchreid unavailable (%s). "
                "Falling back to colour-histogram Re-ID. "
                "Re-entry detection will work but with lower accuracy.",
                exc,
            )
            return False

    def extract(self, frame: np.ndarray, bbox: Tuple) -> Optional[np.ndarray]:
        """Return a normalised embedding vector for a person crop."""
        import cv2

        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        h, w = frame.shape[:2]
        x1, x2 = max(0, x1), min(w, x2)
        y1, y2 = max(0, y1), min(h, y2)
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            return None

        if self._use_osnet:
            return self._osnet_embedding(crop)
        return self._histogram_embedding(frame, crop)

    def _osnet_embedding(self, crop: np.ndarray) -> np.ndarray:
        import torch
        import cv2

        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        tensor = self._transforms(rgb).unsqueeze(0)
        with torch.no_grad():
            emb = self._model(tensor).squeeze().numpy()
        norm = np.linalg.norm(emb)
        return emb / (norm + 1e-8)

    def _histogram_embedding(self, frame: np.ndarray, crop: np.ndarray) -> np.ndarray:
        """32-bin per-channel HSV histogram → 96-dim embedding."""
        import cv2

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hist = []
        for ch in range(3):
            h = cv2.calcHist([hsv], [ch], None, [32], [0, 256])
            hist.extend(h.flatten())
        vec = np.array(hist, dtype=np.float32)
        norm = np.linalg.norm(vec)
        return vec / (norm + 1e-8)

    @staticmethod
    def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


# ---------------------------------------------------------------------------
# Main tracker
# ---------------------------------------------------------------------------

class VisitorTracker:
    """
    One instance per store. Shared across all clips so re-entry detection
    works even when a visitor exits on one clip and re-enters on another.
    """

    def __init__(self, config: PipelineConfig, store_id: str):
        self.config = config
        self.store_id = store_id
        self.reid = ReIDModel(config.reid_model)

        # Active tracks: ByteTrack track_id → state
        self._tracks: Dict[int, TrackState] = {}

        # Re-entry registry: recent EXIT records
        self._exit_history: List[ExitRecord] = []

        # Cross-camera registry: visitor_id → latest embedding
        self._visitor_embeddings: Dict[str, np.ndarray] = {}

        # Billing zone: set of visitor_ids currently in billing area
        self._billing_visitors: Set[str] = set()

        # Pending BILLING_QUEUE_ABANDON events to be resolved post-processing
        self.pending_billing_exits: List[BillingExit] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def update(
        self,
        track_id: int,
        bbox: np.ndarray,
        frame: np.ndarray,
        zone_id: Optional[str],
        sku_zone: Optional[str],
        is_staff: bool,
        confidence: float,
        camera_id: str,
        camera_type: str,
        frame_time: datetime,
        entry_threshold_y: float,
    ) -> List[dict]:
        """
        Process one track detection for one frame. Returns events to emit.

        Call this once per (track_id, frame). Multiple tracks in the same
        frame should each call this method independently.
        """
        events: List[dict] = []

        # ── 1. Resolve visitor identity ────────────────────────────────────
        embedding = self.reid.extract(frame, bbox)
        centroid_y = float((bbox[1] + bbox[3]) / 2)

        if track_id not in self._tracks:
            visitor_id, is_reentry = self._assign_visitor_id(
                embedding, is_staff, camera_type
            )
            state = TrackState(
                track_id=track_id,
                visitor_id=visitor_id,
                camera_id=camera_id,
                is_staff=is_staff,
                confidence=confidence,
                embedding=embedding,
                prev_y=centroid_y,
            )
            self._tracks[track_id] = state

            # REENTRY event (replaces ENTRY for returning visitors)
            if is_reentry:
                state.has_entered = True
                events.append(self._make_event(state, "REENTRY", ts=frame_time))
                if embedding is not None:
                    self._visitor_embeddings[visitor_id] = embedding
        else:
            state = self._tracks[track_id]
            if embedding is not None:
                state.embedding = embedding
                self._visitor_embeddings[state.visitor_id] = embedding

        # ── 2. Entry / exit detection (entry camera only) ─────────────────
        if camera_type == "entry_exit" and state.prev_y is not None:
            events.extend(
                self._check_threshold_crossing(state, centroid_y, entry_threshold_y, frame_time)
            )
        state.prev_y = centroid_y

        # ── 3. Zone transition ────────────────────────────────────────────
        events.extend(self._update_zone(state, zone_id, sku_zone, frame_time))

        return events

    def on_track_lost(self, track_id: int, frame_time: datetime) -> List[dict]:
        """
        ByteTrack dropped this track. Emit ZONE_EXIT if visitor was in a zone.
        Do NOT emit EXIT here — that requires an explicit threshold crossing.
        """
        events: List[dict] = []
        state = self._tracks.pop(track_id, None)
        if state is None:
            return events

        if state.current_zone is not None:
            dwell_ms = self._zone_dwell_ms(state, frame_time)
            events.append(
                self._make_event(state, "ZONE_EXIT",
                                 zone_id=state.current_zone,
                                 sku_zone=state.current_sku,
                                 dwell_ms=dwell_ms,
                                 ts=frame_time)
            )
            if state.in_billing:
                self._record_billing_exit(state, dwell_ms, frame_time)
                self._billing_visitors.discard(state.visitor_id)

        return events

    def flush(self, end_time: datetime) -> List[dict]:
        """Emit final ZONE_EXIT for all tracks still active at clip end."""
        events: List[dict] = []
        for tid in list(self._tracks):
            events.extend(self.on_track_lost(tid, end_time))
        return events

    # ── Identity resolution ──────────────────────────────────────────────────

    def _assign_visitor_id(
        self,
        embedding: Optional[np.ndarray],
        is_staff: bool,
        camera_type: str,
    ) -> Tuple[str, bool]:
        """
        Return (visitor_id, is_reentry).

        Priority:
          1. Cross-camera match → reuse existing visitor_id (same session)
          2. Re-entry match     → reuse visitor_id + flag REENTRY
          3. New visitor        → fresh VIS_xxxxxx
        """
        if embedding is not None:
            # Cross-camera dedup
            for vid, emb in self._visitor_embeddings.items():
                if self.reid.cosine_sim(embedding, emb) > self.config.reid_sim_threshold:
                    logger.debug("Cross-camera match: %s", vid)
                    return vid, False

            # Re-entry check
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(minutes=self.config.reid_window_minutes)
            self._exit_history = [r for r in self._exit_history if r.exit_time > cutoff]

            for record in self._exit_history:
                if record.store_id != self.store_id:
                    continue
                if self.reid.cosine_sim(embedding, record.embedding) > self.config.reid_sim_threshold:
                    logger.debug("Re-entry detected: %s", record.visitor_id)
                    return record.visitor_id, True

        visitor_id = f"VIS_{uuid.uuid4().hex[:6]}"
        return visitor_id, False

    # ── Threshold crossing ────────────────────────────────────────────────────

    def _check_threshold_crossing(
        self,
        state: TrackState,
        curr_y: float,
        threshold_y: float,
        ts: datetime,
    ) -> List[dict]:
        events: List[dict] = []
        prev_y = state.prev_y

        crossed_inbound = prev_y < threshold_y <= curr_y
        crossed_outbound = prev_y >= threshold_y > curr_y

        if crossed_inbound and not state.has_entered:
            state.has_entered = True
            if state.visitor_id in [r.visitor_id for r in self._exit_history]:
                events.append(self._make_event(state, "REENTRY", ts=ts))
            else:
                events.append(self._make_event(state, "ENTRY", ts=ts))
            if state.embedding is not None:
                self._visitor_embeddings[state.visitor_id] = state.embedding

        elif crossed_outbound and state.has_entered:
            state.has_entered = False
            events.append(self._make_event(state, "EXIT", ts=ts))
            if state.embedding is not None:
                self._exit_history.append(ExitRecord(
                    visitor_id=state.visitor_id,
                    embedding=state.embedding,
                    exit_time=ts,
                    store_id=self.store_id,
                ))

        return events

    # ── Zone tracking ─────────────────────────────────────────────────────────

    def _update_zone(
        self,
        state: TrackState,
        new_zone: Optional[str],
        new_sku: Optional[str],
        ts: datetime,
    ) -> List[dict]:
        events: List[dict] = []

        if new_zone != state.current_zone:
            # ── zone exit ──────────────────────────────────────────────────
            if state.current_zone is not None:
                dwell_ms = self._zone_dwell_ms(state, ts)
                events.append(
                    self._make_event(state, "ZONE_EXIT",
                                     zone_id=state.current_zone,
                                     sku_zone=state.current_sku,
                                     dwell_ms=dwell_ms,
                                     ts=ts)
                )
                if state.in_billing:
                    self._record_billing_exit(state, dwell_ms, ts)
                    self._billing_visitors.discard(state.visitor_id)
                    state.in_billing = False

            # ── zone enter ─────────────────────────────────────────────────
            if new_zone is not None:
                events.append(
                    self._make_event(state, "ZONE_ENTER",
                                     zone_id=new_zone,
                                     sku_zone=new_sku,
                                     ts=ts)
                )
                state.zone_entry_time = ts
                state.last_dwell_emit = ts

                if self._is_billing(new_zone) and not state.is_staff:
                    # Per spec: "Visitor enters billing zone while queue_depth > 0"
                    # — only emit when there is ALREADY at least one person in the
                    # billing zone before this visitor joins.  The first person at
                    # the counter is being served, not queuing.
                    existing_depth = len(self._billing_visitors)
                    self._billing_visitors.add(state.visitor_id)
                    if existing_depth > 0:
                        events.append(
                            self._make_event(state, "BILLING_QUEUE_JOIN",
                                             zone_id=new_zone,
                                             sku_zone=new_sku,
                                             queue_depth=existing_depth,
                                             ts=ts)
                        )
                    state.in_billing = True
                    state.billing_entry_time = ts

            state.current_zone = new_zone
            state.current_sku = new_sku

        elif new_zone is not None and state.last_dwell_emit is not None:
            # ── zone dwell tick ────────────────────────────────────────────
            elapsed = (ts - state.last_dwell_emit).total_seconds()
            if elapsed >= self.config.dwell_interval_seconds:
                events.append(
                    self._make_event(state, "ZONE_DWELL",
                                     zone_id=new_zone,
                                     sku_zone=new_sku,
                                     dwell_ms=int(elapsed * 1000),
                                     ts=ts)
                )
                state.last_dwell_emit = ts

        return events

    # ── Billing abandon ────────────────────────────────────────────────────────

    def _record_billing_exit(
        self, state: TrackState, dwell_ms: int, ts: datetime
    ) -> None:
        """Buffer a billing exit; resolved post-processing via resolve_abandons()."""
        self.pending_billing_exits.append(BillingExit(
            visitor_id=state.visitor_id,
            camera_id=state.camera_id,
            is_staff=state.is_staff,
            confidence=state.confidence,
            zone_id=state.current_zone or "BILLING",
            sku_zone=state.current_sku,
            dwell_ms=dwell_ms,
            exit_time=ts,
            session_seq=state.session_seq,
        ))

    def resolve_abandons(self, pos_transactions: List[dict]) -> List[dict]:
        """
        Post-processing: emit BILLING_QUEUE_ABANDON for visitors who left the
        billing zone without a POS transaction in the next 5 minutes.

        Call this AFTER processing all clips for the store.
        """
        events: List[dict] = []
        for record in self.pending_billing_exits:
            window_end = record.exit_time + timedelta(minutes=5)
            converted = any(
                _parse_ts(txn["timestamp"]) is not None
                and record.exit_time <= _parse_ts(txn["timestamp"]) <= window_end
                and txn.get("store_id") == self.store_id
                for txn in pos_transactions
            )
            if not converted:
                events.append({
                    "event_id": str(uuid.uuid4()),
                    "store_id": self.store_id,
                    "camera_id": record.camera_id,
                    "visitor_id": record.visitor_id,
                    "event_type": "BILLING_QUEUE_ABANDON",
                    "timestamp": _fmt_ts(record.exit_time),
                    "zone_id": record.zone_id,
                    "dwell_ms": record.dwell_ms,
                    "is_staff": record.is_staff,
                    "confidence": record.confidence,
                    "metadata": {
                        "queue_depth": None,
                        "sku_zone": record.sku_zone,
                        "session_seq": record.session_seq + 1,
                    },
                })
        self.pending_billing_exits.clear()
        return events

    # ── Private helpers ────────────────────────────────────────────────────────

    def _make_event(
        self,
        state: TrackState,
        event_type: str,
        *,
        zone_id: Optional[str] = None,
        sku_zone: Optional[str] = None,
        dwell_ms: int = 0,
        queue_depth: Optional[int] = None,
        ts: Optional[datetime] = None,
    ) -> dict:
        return {
            "event_id": str(uuid.uuid4()),
            "store_id": self.store_id,
            "camera_id": state.camera_id,
            "visitor_id": state.visitor_id,
            "event_type": event_type,
            "timestamp": _fmt_ts(ts or datetime.now(timezone.utc)),
            "zone_id": zone_id,
            "dwell_ms": dwell_ms,
            "is_staff": state.is_staff,
            "confidence": round(state.confidence, 4),
            "metadata": {
                "queue_depth": queue_depth,
                "sku_zone": sku_zone,
                "session_seq": state.next_seq(),
            },
        }

    def _is_billing(self, zone_id: Optional[str]) -> bool:
        if not zone_id:
            return False
        upper = zone_id.upper()
        return any(kw in upper for kw in self.config.billing_keywords)

    @staticmethod
    def _zone_dwell_ms(state: TrackState, now: datetime) -> int:
        if state.zone_entry_time is None:
            return 0
        return int((now - state.zone_entry_time).total_seconds() * 1000)


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _fmt_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts_str: str) -> Optional[datetime]:
    try:
        s = ts_str.rstrip("Z")
        if "+" in s:
            s = s.split("+")[0]
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except Exception:
        return None
