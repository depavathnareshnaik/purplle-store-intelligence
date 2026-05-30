"""
Real-time metrics and heatmap computation.

All queries filter to today's date (UTC) and exclude is_staff=true visitors.
Every function returns zero / empty-safe values — a store with no events
must return valid JSON, never a 500 or null fields.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas import HeatmapResponse, MetricsResponse, ZoneHeatmap

logger = logging.getLogger("api.metrics")

LOW_CONFIDENCE_SESSION_THRESHOLD = 20


def _active_date(store_id: str, db: Session) -> date:
    """
    Return the date that has events for this store.
    Falls back to today if no events exist.
    This handles both real historical data (e.g. 2026-04-10) and live data.
    """
    row = db.execute(
        text("SELECT MAX(timestamp::date) AS active_date FROM events WHERE store_id = :sid"),
        {"sid": store_id},
    ).fetchone()
    if row and row.active_date:
        return row.active_date
    return datetime.now(timezone.utc).date()


def get_metrics(store_id: str, db: Session) -> MetricsResponse:
    today = _active_date(store_id, db)

    unique_visitors = _unique_visitors(store_id, today, db)
    conversion_rate = _conversion_rate(store_id, today, db)
    avg_dwell_by_zone = _avg_dwell_by_zone(store_id, today, db)
    queue_depth = _current_queue_depth(store_id, db)
    abandonment_rate = _abandonment_rate(store_id, today, db)

    return MetricsResponse(
        store_id=store_id,
        date=str(today),
        unique_visitors=unique_visitors,
        conversion_rate=conversion_rate,
        avg_dwell_by_zone=avg_dwell_by_zone,
        queue_depth=queue_depth,
        abandonment_rate=abandonment_rate,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


def get_heatmap(store_id: str, db: Session) -> HeatmapResponse:
    today = _active_date(store_id, db)

    session_count = _unique_visitors(store_id, today, db)
    confidence = "low" if session_count < LOW_CONFIDENCE_SESSION_THRESHOLD else "ok"

    zones = _zone_heatmap_data(store_id, today, db)
    _normalize_scores(zones)

    return HeatmapResponse(
        store_id=store_id,
        data_confidence=confidence,
        zones=zones,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Individual metric queries
# ---------------------------------------------------------------------------

def _unique_visitors(store_id: str, query_date: date, db: Session) -> int:
    """Distinct non-staff visitors who entered the store today."""
    row = db.execute(
        text("""
            SELECT COUNT(DISTINCT visitor_id) AS cnt
            FROM sessions
            WHERE store_id    = :store_id
              AND session_date = :date
              AND is_staff     = false
        """),
        {"store_id": store_id, "date": query_date},
    ).fetchone()
    return int(row.cnt) if row else 0


def _conversion_rate(store_id: str, query_date: date, db: Session) -> float:
    """
    Fraction of today's visitors who converted.

    Correlation rule (from problem statement):
      A visitor is converted when they were in the billing zone within the
      5-minute window BEFORE any POS transaction timestamp at this store.

    Uses BILLING_QUEUE_JOIN events as the billing-zone presence signal
    because those are the events the pipeline emits with queue_depth context.
    """
    row = db.execute(
        text("""
            WITH session_visitors AS (
                -- All non-staff visitors for the store today
                SELECT DISTINCT visitor_id
                FROM sessions
                WHERE store_id    = :store_id
                  AND session_date = :date
                  AND is_staff     = false
            ),
            billing_moments AS (
                -- Each moment a visitor was in the billing zone today
                SELECT e.visitor_id, e.timestamp AS billing_ts
                FROM events e
                JOIN session_visitors sv ON sv.visitor_id = e.visitor_id
                WHERE e.store_id   = :store_id
                  AND e.event_type = 'BILLING_QUEUE_JOIN'
                  AND e.timestamp::date = :date
            ),
            converted AS (
                -- Visitors whose billing moment falls within 5 min before a transaction
                SELECT DISTINCT bm.visitor_id
                FROM billing_moments bm
                JOIN pos_transactions p ON p.store_id = :store_id
                    AND bm.billing_ts BETWEEN p.timestamp - INTERVAL '5 minutes'
                                          AND p.timestamp
            )
            SELECT
                (SELECT COUNT(*) FROM session_visitors) AS total,
                (SELECT COUNT(*) FROM converted)        AS converted_count
        """),
        {"store_id": store_id, "date": query_date},
    ).fetchone()

    if not row or not row.total:
        return 0.0
    return round(row.converted_count / row.total, 4)


def _avg_dwell_by_zone(
    store_id: str, query_date: date, db: Session
) -> Dict[str, float]:
    """
    Average dwell time per zone in milliseconds, using ZONE_DWELL events.
    ZONE_DWELL is emitted every 30s of continuous presence, so AVG(dwell_ms)
    gives the rolling average tick duration — meaningful for heatmap ranking.
    """
    rows = db.execute(
        text("""
            SELECT zone_id, ROUND(AVG(dwell_ms), 0) AS avg_dwell_ms
            FROM events
            WHERE store_id    = :store_id
              AND event_type  = 'ZONE_DWELL'
              AND is_staff    = false
              AND timestamp::date = :date
              AND zone_id IS NOT NULL
            GROUP BY zone_id
            ORDER BY zone_id
        """),
        {"store_id": store_id, "date": query_date},
    ).fetchall()
    return {row.zone_id: float(row.avg_dwell_ms) for row in rows}


def _current_queue_depth(store_id: str, db: Session) -> int:
    """
    People currently in the billing area:
    sessions that reached billing and have not yet exited the store.
    """
    row = db.execute(
        text("""
            SELECT COUNT(DISTINCT visitor_id) AS depth
            FROM sessions
            WHERE store_id       = :store_id
              AND reached_billing = true
              AND exit_time IS NULL
              AND is_staff        = false
        """),
        {"store_id": store_id},
    ).fetchone()
    return int(row.depth) if row else 0


def _abandonment_rate(store_id: str, query_date: date, db: Session) -> float:
    """
    Fraction of billing queue joins that ended in abandonment (no purchase).
    abandonment_rate = BILLING_QUEUE_ABANDON count / BILLING_QUEUE_JOIN count
    Returns 0.0 when there are no joins (no division by zero).
    """
    row = db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE event_type = 'BILLING_QUEUE_ABANDON') AS abandon_count,
                COUNT(*) FILTER (WHERE event_type = 'BILLING_QUEUE_JOIN')    AS join_count
            FROM events
            WHERE store_id  = :store_id
              AND event_type IN ('BILLING_QUEUE_JOIN', 'BILLING_QUEUE_ABANDON')
              AND is_staff   = false
              AND timestamp::date = :date
        """),
        {"store_id": store_id, "date": query_date},
    ).fetchone()

    if not row or not row.join_count:
        return 0.0
    return round(row.abandon_count / row.join_count, 4)


# ---------------------------------------------------------------------------
# Heatmap helpers
# ---------------------------------------------------------------------------

def _zone_heatmap_data(
    store_id: str, query_date: date, db: Session
) -> List[ZoneHeatmap]:
    """
    Per-zone: distinct visitor count (from ZONE_ENTER) and
    average dwell time (from ZONE_DWELL events only).
    """
    rows = db.execute(
        text("""
            SELECT
                zone_id,
                COUNT(DISTINCT visitor_id)
                    FILTER (WHERE event_type = 'ZONE_ENTER')  AS visit_count,
                COALESCE(
                    AVG(dwell_ms)
                    FILTER (WHERE event_type = 'ZONE_DWELL'), 0
                )                                             AS avg_dwell_ms
            FROM events
            WHERE store_id   = :store_id
              AND event_type  IN ('ZONE_ENTER', 'ZONE_DWELL')
              AND is_staff    = false
              AND timestamp::date = :date
              AND zone_id IS NOT NULL
            GROUP BY zone_id
            HAVING COUNT(DISTINCT visitor_id)
                FILTER (WHERE event_type = 'ZONE_ENTER') > 0
            ORDER BY visit_count DESC
        """),
        {"store_id": store_id, "date": query_date},
    ).fetchall()

    return [
        ZoneHeatmap(
            zone_id=row.zone_id,
            visit_count=int(row.visit_count),
            avg_dwell_ms=float(row.avg_dwell_ms),
            normalized_score=0.0,   # filled in by _normalize_scores
        )
        for row in rows
    ]


def _normalize_scores(zones: List[ZoneHeatmap]) -> None:
    """Normalize visit_count to 0–100 in-place. Busiest zone = 100."""
    if not zones:
        return
    max_count = max(z.visit_count for z in zones) or 1
    for z in zones:
        z.normalized_score = round(z.visit_count / max_count * 100, 1)
