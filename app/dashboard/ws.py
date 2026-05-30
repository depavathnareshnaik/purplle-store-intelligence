"""
Live dashboard — HTTP route (serves HTML) + WebSocket (streams metrics).

Architecture:
  GET /dashboard           → serves app/dashboard/index.html
  WS  /ws/{store_id}       → polls all analytics endpoints every 2 s,
                             broadcasts a consolidated JSON payload to
                             every connected browser tab for that store.

Each WebSocket connection runs an independent polling loop (asyncio.sleep).
No Redis or in-process pub/sub needed — at dashboard scale (< 10 concurrent
tabs) independent polling is cheaper and simpler than a broadcast bus.

The payload includes all four metric categories so the browser makes exactly
ONE connection to get everything it needs to render.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from app.anomalies import get_anomalies
from app.db import SessionLocal
from app.funnel import get_funnel
from app.metrics import get_heatmap, get_metrics

logger = logging.getLogger("api.dashboard")
router = APIRouter(tags=["dashboard"])

# How often the server recomputes and pushes metrics to each client
POLL_INTERVAL_SECONDS: float = 2.0

_HTML_PATH = Path(__file__).parent / "index.html"


# ---------------------------------------------------------------------------
# HTTP — serve the dashboard page
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page() -> HTMLResponse:
    """
    Serve the live dashboard single-page app.

    The HTML file contains all CSS, JS, and Chart.js initialisation inline —
    no build step, no CDN dependencies beyond Chart.js (loaded from jsDelivr).
    """
    return HTMLResponse(content=_HTML_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# WebSocket — stream live metrics
# ---------------------------------------------------------------------------

@router.websocket("/ws/{store_id}")
async def websocket_dashboard(websocket: WebSocket, store_id: str) -> None:
    """
    Stream a consolidated metrics payload every POLL_INTERVAL_SECONDS.

    Payload shape:
    {
      "store_id":  str,
      "ts":        "HH:MM:SS" (UTC),
      "metrics":   { unique_visitors, conversion_rate_pct, queue_depth,
                     abandonment_rate_pct, avg_dwell_by_zone },
      "funnel":    [ { stage, count, drop_off_pct }, ... ],
      "heatmap":   [ { zone_id, visit_count, score }, ... ],
      "anomalies": [ { type, severity, action }, ... ],
      "data_confidence": "ok" | "low"
    }
    On any error a { "store_id", "ts", "error" } dict is sent instead.
    """
    await websocket.accept()
    logger.info("Dashboard connected — store: %s", store_id)

    try:
        while True:
            payload = _build_payload(store_id)
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        logger.info("Dashboard disconnected — store: %s", store_id)
    except Exception as exc:
        logger.warning("WebSocket error (store=%s): %s", store_id, exc)


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def _build_payload(store_id: str) -> Dict[str, Any]:
    """Query all analytics modules and assemble a single broadcast dict."""
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
    db = SessionLocal()
    try:
        metrics    = get_metrics(store_id, db)
        funnel     = get_funnel(store_id, db)
        heatmap    = get_heatmap(store_id, db)
        anomalies  = get_anomalies(store_id, db)

        return {
            "store_id": store_id,
            "ts": now_str,
            "metrics": {
                "unique_visitors":       metrics.unique_visitors,
                "conversion_rate_pct":   round(metrics.conversion_rate * 100, 1),
                "queue_depth":           metrics.queue_depth,
                "abandonment_rate_pct":  round(metrics.abandonment_rate * 100, 1),
                "avg_dwell_by_zone":     metrics.avg_dwell_by_zone,
            },
            "funnel": [
                {
                    "stage":        s.stage,
                    "count":        s.count,
                    "drop_off_pct": s.drop_off_pct,
                }
                for s in funnel
            ],
            "heatmap": [
                {
                    "zone_id":     z.zone_id,
                    "visit_count": z.visit_count,
                    "score":       z.normalized_score,
                }
                for z in heatmap.zones
            ],
            "anomalies": [
                {
                    "type":     a.type,
                    "severity": a.severity,
                    "action":   a.suggested_action,
                }
                for a in anomalies.anomalies
            ],
            "data_confidence": heatmap.data_confidence,
        }

    except Exception as exc:
        logger.error("Payload build failed (store=%s): %s", store_id, exc)
        return {"store_id": store_id, "ts": now_str, "error": str(exc)}
    finally:
        db.close()
