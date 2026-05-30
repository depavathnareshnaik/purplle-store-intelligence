"""
Conversion funnel computation.

Funnel stages (in order):
  entry          → unique visitors who entered the store today
  zone_visit     → subset who visited at least one product zone
  billing_queue  → subset who reached the billing area
  purchase       → subset who completed a purchase (POS correlation)

Key constraint: SESSION is the unit, not raw events.
  COUNT(DISTINCT visitor_id) ensures a visitor who re-enters counts once,
  not once per ENTRY event they generated.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas import FunnelStage

logger = logging.getLogger("api.funnel")


def get_funnel(store_id: str, db: Session) -> List[FunnelStage]:
    from app.metrics import _active_date
    today = _active_date(store_id, db)

    entry_count    = _count_entries(store_id, today, db)
    zone_count     = _count_zone_visitors(store_id, today, db)
    billing_count  = _count_billing_visitors(store_id, today, db)
    purchase_count = _count_purchasers(store_id, today, db)

    return [
        FunnelStage(
            stage="entry",
            count=entry_count,
            drop_off_pct=0.0,                               # baseline stage
        ),
        FunnelStage(
            stage="zone_visit",
            count=zone_count,
            drop_off_pct=_drop_off(entry_count, zone_count),
        ),
        FunnelStage(
            stage="billing_queue",
            count=billing_count,
            drop_off_pct=_drop_off(zone_count, billing_count),
        ),
        FunnelStage(
            stage="purchase",
            count=purchase_count,
            drop_off_pct=_drop_off(billing_count, purchase_count),
        ),
    ]


# ---------------------------------------------------------------------------
# Stage counters
# ---------------------------------------------------------------------------

def _count_entries(store_id: str, query_date, db: Session) -> int:
    """
    Unique non-staff visitors who entered the store today.
    COUNT(DISTINCT visitor_id) means a visitor who re-enters is counted once.
    """
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


def _count_zone_visitors(store_id: str, query_date, db: Session) -> int:
    """
    Unique visitors who entered at least one product zone.
    Uses the visited_zones array on the sessions table (populated at ingest time).
    cardinality() handles empty arrays correctly (returns 0, not NULL).
    """
    row = db.execute(
        text("""
            SELECT COUNT(DISTINCT visitor_id) AS cnt
            FROM sessions
            WHERE store_id    = :store_id
              AND session_date = :date
              AND is_staff     = false
              AND cardinality(visited_zones) > 0
        """),
        {"store_id": store_id, "date": query_date},
    ).fetchone()
    return int(row.cnt) if row else 0


def _count_billing_visitors(store_id: str, query_date, db: Session) -> int:
    """
    Unique visitors who reached the billing area.
    reached_billing is set to true when a BILLING_QUEUE_JOIN event is ingested.
    """
    row = db.execute(
        text("""
            SELECT COUNT(DISTINCT visitor_id) AS cnt
            FROM sessions
            WHERE store_id       = :store_id
              AND session_date    = :date
              AND is_staff        = false
              AND reached_billing = true
        """),
        {"store_id": store_id, "date": query_date},
    ).fetchone()
    return int(row.cnt) if row else 0


def _count_purchasers(store_id: str, query_date, db: Session) -> int:
    """
    Unique visitors who completed a purchase.

    Same POS correlation as /metrics:
      visitor's BILLING_QUEUE_JOIN timestamp falls within 5 minutes before
      any POS transaction at this store.
    """
    row = db.execute(
        text("""
            WITH session_visitors AS (
                SELECT DISTINCT visitor_id
                FROM sessions
                WHERE store_id    = :store_id
                  AND session_date = :date
                  AND is_staff     = false
            ),
            billing_moments AS (
                SELECT e.visitor_id, e.timestamp AS billing_ts
                FROM events e
                JOIN session_visitors sv ON sv.visitor_id = e.visitor_id
                WHERE e.store_id   = :store_id
                  AND e.event_type = 'BILLING_QUEUE_JOIN'
                  AND e.timestamp::date = :date
            ),
            purchasers AS (
                SELECT DISTINCT bm.visitor_id
                FROM billing_moments bm
                JOIN pos_transactions p ON p.store_id = :store_id
                    AND bm.billing_ts BETWEEN p.timestamp - INTERVAL '5 minutes'
                                          AND p.timestamp
            )
            SELECT COUNT(*) AS cnt FROM purchasers
        """),
        {"store_id": store_id, "date": query_date},
    ).fetchone()
    return int(row.cnt) if row else 0


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _drop_off(prev: int, current: int) -> float:
    """Percentage of visitors who dropped off between two consecutive stages."""
    if prev == 0:
        return 0.0
    return round((prev - current) / prev * 100, 2)
