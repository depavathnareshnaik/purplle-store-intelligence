"""
Zone classification via polygon point-in-polygon lookup.

Reads zone polygon coordinates from store_layout.json and classifies
each (x, y) centroid into a named zone.  Returns (None, None) for
coordinates that fall outside all defined polygons (common areas,
aisles, etc.).

The shapely library is used for polygon geometry — it handles concave
polygons, holes, and edge cases that a naive bounding-box approach misses.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger("pipeline.zone_classifier")


class ZoneClassifier:
    """
    Stateless classifier: loads polygon definitions once, classifies many points.

    store_layout.json expected structure (per store):
    {
      "STORE_BLR_002": {
        "zones": [
          {
            "zone_id": "SKINCARE",
            "sku_zone": "MOISTURISER",
            "polygon": [[x1,y1], [x2,y2], ...]   ← pixel coordinates
          }
        ]
      }
    }
    """

    def __init__(self, layout_path: Path):
        self._store_zones: Dict[str, list] = {}   # store_id → list of zone dicts
        self._load(layout_path)

    def _load(self, layout_path: Path) -> None:
        if not layout_path.exists():
            logger.warning(
                "store_layout.json not found at %s — zone classification disabled. "
                "All zone_id fields will be null until the file is provided.",
                layout_path,
            )
            return

        with open(layout_path, encoding="utf-8") as fh:
            layout: dict = json.load(fh)

        for store_id, store_data in layout.items():
            zones = []
            for z in store_data.get("zones", []):
                try:
                    from shapely.geometry import Polygon

                    zones.append({
                        "zone_id": z["zone_id"],
                        "sku_zone": z.get("sku_zone", z["zone_id"]),
                        "polygon": Polygon(z["polygon"]),
                    })
                except Exception as exc:
                    logger.warning("Skipping malformed zone %s: %s", z.get("zone_id"), exc)
            self._store_zones[store_id] = zones
            logger.info("Loaded %d zones for %s", len(zones), store_id)

    def classify(
        self, store_id: str, cx: float, cy: float
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Return (zone_id, sku_zone) for the centroid (cx, cy) in pixel space.
        Returns (None, None) if the point is not inside any defined zone.

        Iterates zones in definition order — first match wins, so ordering
        in store_layout.json matters for overlapping zones.
        """
        zones = self._store_zones.get(store_id, [])
        if not zones:
            return None, None

        from shapely.geometry import Point

        pt = Point(cx, cy)
        for zone in zones:
            if zone["polygon"].contains(pt):
                return zone["zone_id"], zone["sku_zone"]
        return None, None

    def get_camera_info(self, store_id: str, clip_filename: str) -> Tuple[str, str, int]:
        """
        Resolve (camera_id, camera_type, entry_threshold_y_px) from clip filename.

        Matching strategy: look for camera_id in the filename.
        Falls back to heuristics when store_layout.json is not loaded.

        Returns:
          camera_id   — e.g. "CAM_ENTRY_01"
          camera_type — one of "entry_exit", "main_floor", "billing"
          threshold_y — y-coordinate of the entry line in pixels (0 if non-entry camera)
        """
        from pipeline.config import DEFAULT_CONFIG

        # Try to match by 'filename' field in store_layout.json cameras
        store_data = self._raw_layout.get(store_id, {}) if hasattr(self, "_raw_layout") else {}
        clip_base = Path(clip_filename).name  # e.g. "CAM_3.mp4"

        for cam in store_data.get("cameras", []):
            cam_filename = cam.get("filename", "")
            cam_id       = cam["camera_id"]
            # Match by exact filename OR cam_id substring
            if (cam_filename and cam_filename.lower() == clip_base.lower()) or \
               (cam_id.lower().replace("_", "") in clip_base.lower().replace("_", "")):
                cam_type = cam.get("type", "main_floor")
                y_pct    = cam.get("entry_threshold_y_pct", DEFAULT_CONFIG.default_entry_threshold_y_pct)
                # Skip storage cameras — not useful for analytics
                if cam_type == "storage":
                    return cam_id, "storage", 0.0
                return cam_id, cam_type, y_pct

        # Heuristic fallback for unknown filenames
        name = clip_base.lower()
        if any(k in name for k in ("cam_3", "entry", "door", "entrance", "cam3")):
            return "CAM_ENTRY_01", "entry_exit", DEFAULT_CONFIG.default_entry_threshold_y_pct
        if any(k in name for k in ("cam_5", "cam_4", "bill", "checkout", "cam5")):
            return "CAM_BILL_01", "billing", 0.0
        return "CAM_FLOOR_01", "main_floor", 0.0

    def _load_raw(self, layout_path: Path) -> None:
        """Keep raw layout for camera lookups."""
        if layout_path.exists():
            with open(layout_path, encoding="utf-8") as fh:
                self._raw_layout = json.load(fh)
        else:
            self._raw_layout = {}

    @classmethod
    def from_path(cls, layout_path: Path) -> "ZoneClassifier":
        obj = cls(layout_path)
        obj._load_raw(layout_path)
        return obj
