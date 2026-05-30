"""
Pipeline configuration — all tunable constants in one place.

Every threshold that affects detection accuracy or event quality lives here.
Values are intentionally conservative: we prefer a slightly lower true-positive
rate over generating false positives that contaminate the analytics.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple


@dataclass
class PipelineConfig:

    # ── Detection model ───────────────────────────────────────────────────────
    # Real footage is 1920x1080 @ 30fps (CAM1-3) and 25fps (CAM4-5).
    # Using yolov8n for speed on CPU; swap to yolov9c for GPU.
    model_name: str = "yolov8n.pt"
    conf_threshold: float = 0.35       # min YOLO confidence — tuned for Purplle store lighting
    iou_threshold: float = 0.45        # NMS IoU threshold
    frame_stride: int = 6              # process every 6th frame → 5 fps from 30fps source

    # ── ByteTrack ─────────────────────────────────────────────────────────────
    track_activation_threshold: float = 0.25
    lost_track_buffer: int = 30        # frames a lost track is kept alive before pruning
    minimum_matching_threshold: float = 0.80

    # ── Person Re-ID ──────────────────────────────────────────────────────────
    # OSNet x0.25 is the lightest OSNet variant; runs on CPU in < 10 ms/crop.
    # If torchreid is unavailable the pipeline falls back to colour-histogram embeddings.
    reid_model: str = "osnet_x0_25"
    reid_sim_threshold: float = 0.82   # cosine similarity → re-entry / cross-cam match
    reid_window_minutes: int = 15      # how far back to search for re-entry records

    # ── Staff detection ───────────────────────────────────────────────────────
    # BGR tuples calibrated from actual Purplle Brigade Road footage.
    # Staff wear black uniforms — sampled from CAM_1 footage at ~20:10 IST.
    staff_uniform_bgr: List[Tuple[int, int, int]] = field(default_factory=lambda: [
        (30,  30,  30),    # black uniform (dominant — Purplle store staff)
        (20,  20,  60),    # very dark navy (variation under store lighting)
        (50,  50,  50),    # dark charcoal
    ])
    # Intentionally high (0.55) so misclassification of customers is rare.
    staff_match_fraction: float = 0.55

    # ── Zone dwell ────────────────────────────────────────────────────────────
    dwell_interval_seconds: float = 30.0   # emit ZONE_DWELL every N seconds

    # ── Entry / exit ──────────────────────────────────────────────────────────
    # Default threshold line expressed as a fraction of frame height.
    # Overridden per-camera if store_layout.json provides entry_threshold_y_pct.
    default_entry_threshold_y_pct: float = 0.50

    # ── Billing queue ─────────────────────────────────────────────────────────
    # A zone_id containing any of these strings is treated as the billing area.
    billing_keywords: List[str] = field(default_factory=lambda: ["BILLING", "CHECKOUT"])

    # ── Event emission ────────────────────────────────────────────────────────
    ingest_batch_size: int = 500
    api_url: str = "http://localhost:8000"
    ingest_to_api: bool = True         # set False for dry-run / offline mode

    # ── Data paths ────────────────────────────────────────────────────────────
    clips_dir: Path = Path("data/clips")
    events_dir: Path = Path("data/events")
    layout_path: Path = Path("data/store_layout.json")
    pos_path: Path = Path("data/pos_transactions.csv")


# Singleton used by all pipeline modules
DEFAULT_CONFIG = PipelineConfig()
