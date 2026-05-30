import logging
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal

logger = logging.getLogger("api.health")
router = APIRouter()

# A store feed is considered stale when no events have arrived for this long.
STALE_THRESHOLD_MINUTES = 10


class StoreHealth(BaseModel):
    store_id: str
    last_event_at: Optional[str]
    lag_minutes: Optional[float]
    status: Literal["OK", "STALE_FEED", "NO_DATA"]


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    service: str
    version: str
    database: Literal["connected", "disconnected"]
    stores: List[StoreHealth]
    checked_at: str


@router.get("/health", response_model=HealthResponse, tags=["health"])
def get_health() -> HealthResponse:
    """
    Service liveness and per-store feed freshness check.

    Always returns HTTP 200 — degraded state is expressed in the response body.
    This lets on-call engineers distinguish "API is down" (no response) from
    "API is up but database is unhealthy" (200 + status=degraded).

    STALE_FEED is raised per store when no events have been ingested for
    more than STALE_THRESHOLD_MINUTES (default: 10 minutes).
    """
    settings = get_settings()
    db_status: Literal["connected", "disconnected"] = "connected"
    stores: List[StoreHealth] = []
    now = datetime.now(timezone.utc)

    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))

            rows = db.execute(
                text("""
                    SELECT store_id, MAX(timestamp) AS last_event_at
                    FROM events
                    GROUP BY store_id
                    ORDER BY store_id
                """)
            ).fetchall()

            for row in rows:
                last_event_at: datetime = row.last_event_at
                # Ensure timezone-aware for subtraction
                if last_event_at.tzinfo is None:
                    last_event_at = last_event_at.replace(tzinfo=timezone.utc)

                lag_minutes = (now - last_event_at).total_seconds() / 60
                feed_status: Literal["OK", "STALE_FEED", "NO_DATA"] = (
                    "STALE_FEED" if lag_minutes > STALE_THRESHOLD_MINUTES else "OK"
                )
                stores.append(
                    StoreHealth(
                        store_id=row.store_id,
                        last_event_at=last_event_at.isoformat(),
                        lag_minutes=round(lag_minutes, 1),
                        status=feed_status,
                    )
                )
        finally:
            db.close()

    except Exception as exc:
        db_status = "disconnected"
        logger.warning(
            '{"message": "health check db unreachable", "error_type": "%s"}',
            type(exc).__name__,
        )

    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        database=db_status,
        stores=stores,
        checked_at=now.isoformat(),
    )
