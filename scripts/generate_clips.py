#!/usr/bin/env python3
"""
Generate synthetic CCTV-style video clips for pipeline testing.

Creates 60-second MP4 files (640×480, 15 fps) with:
  - Store floor plan overlaid on a dark background
  - Animated white rectangles (simulating people) moving through zones
  - Entry threshold line visible on the entry camera view
  - Staff person (yellow rectangle) moving through all zones

Output:
  data/clips/STORE_BLR_002/entry_exit.mp4
  data/clips/STORE_BLR_002/main_floor.mp4
  data/clips/STORE_BLR_002/billing.mp4
  (same structure for STORE_DEL_001, STORE_MUM_001)

Requirements:
  pip install opencv-python-headless

NOTE: These are synthetic clips for pipeline testing. The colored rectangles
are NOT detectable by YOLOv9 (which expects real human silhouettes). To test
the pipeline with these clips, run with the mock detector:
  python pipeline/detect.py --store STORE_BLR_002 --no-api
Or ingest events directly (bypasses video):
  python scripts/ingest_events.py
"""

import json
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    print("OpenCV not found. Install it:")
    print("  pip install opencv-python-headless")
    sys.exit(1)

ROOT      = Path(__file__).parent.parent
DATA_DIR  = ROOT / "data"
CLIPS_DIR = DATA_DIR / "clips"

W, H   = 640, 480
FPS    = 15
SECS   = 60
FRAMES = FPS * SECS

# Colours (BGR)
BG_COLOUR     = (20, 20, 30)
ZONE_COLOURS  = {
    "SKINCARE":  (180, 100, 60),
    "HAIRCARE":  (60, 130, 180),
    "FRAGRANCE": (80, 160, 80),
    "MAKEUP":    (140, 60, 160),
    "WELLNESS":  (60, 160, 140),
    "BILLING":   (40, 60, 200),
}
PERSON_COLOUR = (240, 240, 240)   # white rectangle = customer
STAFF_COLOUR  = (0, 220, 220)     # cyan = staff


def load_store(store_id: str) -> dict:
    layout = json.loads((DATA_DIR / "store_layout.json").read_text())
    return layout.get(store_id, {})


def draw_floor(frame: np.ndarray, zones: list) -> None:
    """Draw zone rectangles on the frame."""
    for zone in zones:
        poly = np.array(zone["polygon"], dtype=np.int32)
        x1 = min(p[0] for p in zone["polygon"])
        y1 = min(p[1] for p in zone["polygon"])
        x2 = max(p[0] for p in zone["polygon"])
        y2 = max(p[1] for p in zone["polygon"])
        colour = ZONE_COLOURS.get(zone["zone_id"], (100, 100, 100))
        cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 1)
        cv2.putText(frame, zone["zone_id"][:8], (x1 + 6, y1 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, colour, 1, cv2.LINE_AA)


def draw_person(frame: np.ndarray, cx: float, cy: float,
                colour=PERSON_COLOUR, label: str = "") -> None:
    x1, y1 = int(cx - 18), int(cy - 40)
    x2, y2 = int(cx + 18), int(cy + 40)
    x1, x2 = max(0, x1), min(W, x2)
    y1, y2 = max(0, y1), min(H, y2)
    cv2.rectangle(frame, (x1, y1), (x2, y2), colour, -1)
    if label:
        cv2.putText(frame, label, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX,
                    0.35, colour, 1, cv2.LINE_AA)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def make_entry_clip(store_id: str, store_data: dict, output_path: Path) -> None:
    """Entry/exit camera — shows threshold crossing and door area."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H)
    )

    threshold_y = int(H * 0.55)
    zones = store_data.get("zones", [])

    # Person trajectories: (start_frame, entry_x, path)
    persons = [
        (20,  160, "enter"),  # enters at frame 20
        (80,  240, "enter"),
        (180, 320, "enter"),
        (250, 200, "exit"),   # exits
        (300, 280, "enter"),
        (380, 160, "exit"),
    ]

    for f in range(FRAMES):
        frame = np.full((H, W, 3), BG_COLOUR, dtype=np.uint8)

        # Threshold line
        cv2.line(frame, (0, threshold_y), (W, threshold_y), (0, 200, 60), 1)
        cv2.putText(frame, "ENTRY THRESHOLD", (10, threshold_y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 200, 60), 1)

        # Draw persons
        for start, x, direction in persons:
            elapsed = f - start
            if elapsed < 0 or elapsed > 90:
                continue
            t = elapsed / 90.0
            if direction == "enter":
                cy = lerp(threshold_y - 120, threshold_y + 160, t)
            else:
                cy = lerp(threshold_y + 60, threshold_y - 120, t)
            draw_person(frame, x, cy)

        # Staff always visible, moving side to side
        staff_x = lerp(50, W - 50, (f % (FPS * 8)) / (FPS * 8))
        draw_person(frame, staff_x, threshold_y + 100, STAFF_COLOUR, "STAFF")

        # Frame counter + store label
        cv2.putText(frame, f"{store_id}  CAM:ENTRY  {f//FPS:02d}s",
                    (10, H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
        writer.write(frame)

    writer.release()
    print(f"  ✓  {output_path.relative_to(ROOT)}")


def make_floor_clip(store_id: str, store_data: dict, output_path: Path) -> None:
    """Main floor camera — shows people moving between product zones."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H)
    )

    zones = store_data.get("zones", [z for z in store_data.get("zones", [])
                                      if z["zone_id"] != "BILLING"])

    # Person paths: (start_frame, waypoints [(x,y), ...])
    paths = [
        (30,  [(50, 50), (250, 100), (50, 350)]),
        (90,  [(580, 50), (400, 200), (580, 400)]),
        (150, [(300, 300), (150, 100), (500, 200)]),
        (220, [(100, 400), (350, 100)]),
        (300, [(500, 400), (200, 150), (400, 350)]),
    ]

    for f in range(FRAMES):
        frame = np.full((H, W, 3), BG_COLOUR, dtype=np.uint8)
        draw_floor(frame, zones)

        for start, waypoints in paths:
            elapsed = f - start
            if elapsed < 0:
                continue
            total_steps = len(waypoints) - 1
            step_frames = 120
            total_frames = total_steps * step_frames
            if elapsed > total_frames:
                continue
            seg = int(elapsed / step_frames)
            seg = min(seg, total_steps - 1)
            t = (elapsed - seg * step_frames) / step_frames
            x = lerp(waypoints[seg][0], waypoints[seg + 1][0], t)
            y = lerp(waypoints[seg][1], waypoints[seg + 1][1], t)
            draw_person(frame, x, y)

        # Staff moves in a circuit through all zones
        t = (f % (FPS * 12)) / (FPS * 12)
        circuit = [(80, 120), (550, 120), (550, 360), (80, 360)]
        seg = int(t * len(circuit))
        seg_t = (t * len(circuit)) - seg
        p1 = circuit[seg % len(circuit)]
        p2 = circuit[(seg + 1) % len(circuit)]
        draw_person(frame, lerp(p1[0], p2[0], seg_t), lerp(p1[1], p2[1], seg_t),
                    STAFF_COLOUR, "STAFF")

        cv2.putText(frame, f"{store_id}  CAM:FLOOR  {f//FPS:02d}s",
                    (10, H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
        writer.write(frame)

    writer.release()
    print(f"  ✓  {output_path.relative_to(ROOT)}")


def make_billing_clip(store_id: str, store_data: dict, output_path: Path) -> None:
    """Billing area camera — shows queue building and dispersing."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H)
    )

    billing_zones = [z for z in store_data.get("zones", []) if z["zone_id"] == "BILLING"]

    # Queue: people appear one by one, then leave
    queue_positions = [(280, 200), (340, 200), (280, 260), (340, 260), (310, 320)]

    for f in range(FRAMES):
        frame = np.full((H, W, 3), BG_COLOUR, dtype=np.uint8)
        draw_floor(frame, billing_zones)

        # Queue builds up from frame 60 to 400, then drains
        queue_depth = 0
        if 60 <= f < 400:
            queue_depth = min(5, (f - 60) // 60)
        elif f >= 400:
            queue_depth = max(0, 5 - (f - 400) // 30)

        for i in range(queue_depth):
            if i < len(queue_positions):
                draw_person(frame, *queue_positions[i])

        # Queue depth label
        cv2.putText(frame, f"QUEUE: {queue_depth}", (W // 2 - 40, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 80, 220) if queue_depth > 3 else (0, 180, 60), 2)

        cv2.putText(frame, f"{store_id}  CAM:BILLING  {f//FPS:02d}s",
                    (10, H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
        writer.write(frame)

    writer.release()
    print(f"  ✓  {output_path.relative_to(ROOT)}")


def generate_store_clips(store_id: str) -> None:
    print(f"\n▸ {store_id}")
    store_data = load_store(store_id)
    if not store_data:
        print(f"  Store not found in store_layout.json — skipping")
        return

    clip_dir = CLIPS_DIR / store_id
    make_entry_clip(store_id, store_data, clip_dir / "entry_exit.mp4")
    make_floor_clip(store_id, store_data, clip_dir / "main_floor.mp4")
    make_billing_clip(store_id, store_data, clip_dir / "billing.mp4")


def main() -> None:
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║   Store Intelligence — Synthetic Clip Generator          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"  Resolution: {W}×{H}  |  FPS: {FPS}  |  Duration: {SECS}s per clip\n")

    for store_id in ["STORE_BLR_002", "STORE_DEL_001", "STORE_MUM_001"]:
        generate_store_clips(store_id)

    print(f"""
╔══════════════════════════════════════════════════════════╗
║  Clips generated!                                        ║
╠══════════════════════════════════════════════════════════╣
║  NOTE: These clips contain colored rectangles, not       ║
║  real people. YOLOv9 won't detect them.                  ║
║                                                          ║
║  For full pipeline testing, use real clips from          ║
║  the Purplle dataset.                                    ║
║                                                          ║
║  To test the API without video processing:               ║
║    python scripts/generate_dataset.py                    ║
║    python scripts/ingest_events.py                       ║
╚══════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
