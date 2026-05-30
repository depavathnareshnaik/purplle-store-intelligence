"""
Staff detection via upper-body colour histogram.

Rationale: retail staff wear distinct uniforms. We extract the upper 40% of each
person's bounding box (torso region), compute a HSV colour histogram, and check
whether the dominant colour matches any configured uniform reference colour.

Design choices:
  - Upper body only: avoids confusing customer denim trousers with staff trousers
  - HSV colour space: perceptually uniform; hue captures colour identity regardless
    of lighting variation (the biggest practical challenge in retail CCTV)
  - Conservative threshold (default 60%): we prefer to miss staff → count them as
    customers rather than accidentally exclude real customers from metrics
  - No ML model: fast, explainable, zero additional inference cost

To calibrate for a new store:
    from pipeline.staff_classifier import sample_dominant_colour
    colour = sample_dominant_colour("data/clips/STORE_BLR_002/main_floor.mp4", frame=500)
    # Add the returned BGR tuple to config.staff_uniform_bgr
"""

from __future__ import annotations

import logging
from typing import List, Tuple

import cv2
import numpy as np

from pipeline.config import PipelineConfig

logger = logging.getLogger("pipeline.staff_classifier")

# Upper body is the top fraction of the bounding box
_UPPER_BODY_FRACTION = 0.40


class StaffClassifier:
    def __init__(self, config: PipelineConfig):
        self._match_fraction = config.staff_match_fraction
        self._hsv_ranges = _build_hsv_ranges(config.staff_uniform_bgr)

    def is_staff(self, frame: np.ndarray, bbox: Tuple[float, float, float, float]) -> bool:
        """
        Returns True if the person in bbox is likely a staff member.

        bbox format: (x1, y1, x2, y2) in pixel coordinates.
        Returns False — not staff — on any processing failure so we never
        accidentally exclude a real customer due to a bad crop.
        """
        try:
            return self._classify(frame, bbox)
        except Exception as exc:
            logger.debug("Staff classify failed (treating as customer): %s", exc)
            return False

    def _classify(
        self, frame: np.ndarray, bbox: Tuple[float, float, float, float]
    ) -> bool:
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])

        # Clamp to frame bounds
        h, w = frame.shape[:2]
        x1, x2 = max(0, x1), min(w, x2)
        y1, y2 = max(0, y1), min(h, y2)

        upper_y2 = y1 + max(1, int((y2 - y1) * _UPPER_BODY_FRACTION))
        roi = frame[y1:upper_y2, x1:x2]

        if roi.size == 0:
            return False

        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        total = roi.shape[0] * roi.shape[1]

        for lower, upper in self._hsv_ranges:
            matching = int(np.sum(cv2.inRange(hsv_roi, lower, upper) > 0))
            if matching / total >= self._match_fraction:
                return True

        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_hsv_ranges(
    bgr_colours: List[Tuple[int, int, int]],
    hue_tol: int = 20,
    sv_tol: int = 60,
) -> list:
    """Convert BGR reference colours to HSV (lower, upper) tuples for cv2.inRange."""
    ranges = []
    for bgr in bgr_colours:
        pixel = np.uint8([[list(bgr)]])
        hsv = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0][0]
        lower = np.array([
            max(0,   int(hsv[0]) - hue_tol),
            max(0,   int(hsv[1]) - sv_tol),
            max(0,   int(hsv[2]) - sv_tol),
        ])
        upper = np.array([
            min(179, int(hsv[0]) + hue_tol),
            min(255, int(hsv[1]) + sv_tol),
            min(255, int(hsv[2]) + sv_tol),
        ])
        ranges.append((lower, upper))
    return ranges


def sample_dominant_colour(
    video_path: str, frame_idx: int = 300, person_bbox: Tuple = None
) -> Tuple[int, int, int]:
    """
    Utility: sample the dominant BGR colour of a person crop in a clip.
    Used to calibrate staff_uniform_bgr in config.

    Usage:
        colour = sample_dominant_colour("data/clips/store/floor.mp4", frame_idx=500)
        print(f"Add {colour} to staff_uniform_bgr in config.py")
    """
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        raise RuntimeError(f"Could not read frame {frame_idx} from {video_path}")

    if person_bbox:
        x1, y1, x2, y2 = [int(v) for v in person_bbox]
        roi = frame[y1:y1 + int((y2 - y1) * _UPPER_BODY_FRACTION), x1:x2]
    else:
        # Use the centre strip of the frame as a proxy
        h, w = frame.shape[:2]
        roi = frame[h // 3: 2 * h // 3, w // 4: 3 * w // 4]

    # Find dominant colour by k-means with k=1
    pixels = roi.reshape(-1, 3).astype(np.float32)
    _, _, centres = cv2.kmeans(
        pixels, 1, None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0),
        3, cv2.KMEANS_RANDOM_CENTERS,
    )
    bgr = tuple(int(c) for c in centres[0])
    logger.info("Dominant colour: BGR%s", bgr)
    return bgr
