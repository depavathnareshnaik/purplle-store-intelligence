"""
Anomaly detection — three types, all computed from live event data.

QUEUE_SPIKE      — current billing queue depth vs 7-day same-hour average
CONVERSION_DROP  — today's conversion rate vs 7-day trailing average
DEAD_ZONE        — product zone with no ZONE_ENTER in the past 30 minutes
                   (only flagged when the store has had recent activity)

Severities:
  INFO     — noteworthy, no immediate action required
  WARN     — should be investigated within the hour
  CRITICAL — requires immediate action

Baselines are computed on-the-fly from the events table.
If fewer than 2 days of history exist for a metric, that anomaly check is skipped
(returning a baseline would be meaningless noise).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.metrics import _conversion_rate, _current_queue_depth
from app.schemas import Anomaly, AnomaliesResponse

logger = logging.getLogger("api.anomalies")

# Thresholds
QUEUE_SPIKE_WARN_MULTIPLIER     = 2.0
QUEUE_SPIKE_CRITICAL_MULTIPLIER = 3.0
CONVERSION_WARN_RATIO           = 0.80   # today < 80% of 7d avg → WARN
CONVERSION_CRITICAL_RATIO       = 0.60   # today < 60% of 7d avg → CRITICAL
DEAD_ZONE_WINDOW_MINUTES        = 30
STORE_ACTIVE_WINDOW_MINUTES     = 60     # store is considered open if events in last 60 min
MIN_HISTORY_DAYS                = 2      # need at least this many days to make a baseline


def get_anomalies(store_id: str, db: Session) -> AnomaliesResponse:
    now = datetime.now(timezone.utc)
    today = now.date()
    anomalies: List[Anomaly] = []

    anomalies.extend(_check_queue_spike(store_id, now, db))
    anomalies.extend(_check_conversion_drop(store_id, today, db))
    anomalies.extend(_check_dead_zones(store_id, now, db))

    return AnomaliesResponse(
        store_id=store_id,
        anomalies=anomalies,
        computed_at=now.isoformat(),
    )


# ---------------------------------------------------------------------------
# QUEUE_SPIKE
# ---------------------------------------------------------------------------

def _check_queue_spike(
    store_id: str, now: datetime, db: Session
) -> List[Anomaly]:
    current_depth = _current_queue_depth(store_id, db)

    # 7-day average queue depth at the same hour of day
    row = db.execute(
        text("""
            SELECT
                COUNT(DISTINCT day) AS days_of_data,
                AVG(daily_depth)    AS avg_depth
            FROM (
                SELECT
                    session_date                               AS day,
                    COUNT(DISTINCT visitor_id) FILTER (
                        WHERE reached_billing = true
                          AND is_staff = false
                    )                                          AS daily_depth
                FROM sessions
                WHERE store_id    = :store_id
                  AND session_date BETWEEN CURRENT_DATE - INTERVAL '7 days'
                                      AND CURRENT_DATE - INTERVAL '1 day'
                GROUP BY session_date
            ) t
        """),
        {"store_id": store_id},
    ).fetchone()

    if not row or (row.days_of_data or 0) < MIN_HISTORY_DAYS:
        return []

    baseline_avg = float(row.avg_depth or 0)
    if baseline_avg == 0 or current_depth <= baseline_avg * QUEUE_SPIKE_WARN_MULTIPLIER:
        return []

    if current_depth > baseline_avg * QUEUE_SPIKE_CRITICAL_MULTIPLIER:
        severity = "CRITICAL"
    else:
        severity = "WARN"

    return [
        Anomaly(
            type="QUEUE_SPIKE",
            severity=severity,
            suggested_action="Open an additional billing counter immediately.",
            detected_at=now.isoformat(),
            details={
                "current_depth": current_depth,
                "baseline_avg_7d": round(baseline_avg, 1),
                "ratio": round(current_depth / baseline_avg, 2),
            },
        )
    ]


# ---------------------------------------------------------------------------
# CONVERSION_DROP
# ---------------------------------------------------------------------------

def _check_conversion_drop(
    store_id: str, today, db: Session
) -> List[Anomaly]:
    # Average daily conversion rate over the past 7 days (excluding today)
    row = db.execute(
        text("""
            WITH daily_rates AS (
                SELECT
                    session_date,
                    COUNT(DISTINCT s.visitor_id) FILTER (
                        WHERE s.is_staff = false
                    )                                                   AS total_visitors,
                    COUNT(DISTINCT bm.visitor_id)                       AS converted_visitors
                FROM sessions s
                LEFT JOIN LATERAL (
                    SELECT e.visitor_id
                    FROM events e
                    JOIN pos_transactions p ON p.store_id = s.store_id
                        AND e.timestamp BETWEEN p.timestamp - INTERVAL '5 minutes'
                                            AND p.timestamp
                    WHERE e.visitor_id = s.visitor_id
                      AND e.store_id   = s.store_id
                      AND e.event_type = 'BILLING_QUEUE_JOIN'
                    LIMIT 1
                ) bm ON true
                WHERE s.store_id    = :store_id
                  AND s.session_date BETWEEN CURRENT_DATE - INTERVAL '7 days'
                                        AND CURRENT_DATE - INTERVAL '1 day'
                GROUP BY session_date
            )
            SELECT
                COUNT(*) AS days_of_data,
                AVG(
                    CASE WHEN total_visitors > 0
                         THEN converted_visitors::float / total_visitors
                         ELSE NULL
                    END
                ) AS avg_conversion_rate
            FROM daily_rates
            WHERE total_visitors > 0
        """),
        {"store_id": store_id},
    ).fetchone()

    if not row or (row.days_of_data or 0) < MIN_HISTORY_DAYS:
        return []

    baseline_rate = float(row.avg_conversion_rate or 0)
    if baseline_rate == 0:
        return []

    today_rate = _conversion_rate(store_id, today, db)
    if today_rate >= baseline_rate * CONVERSION_WARN_RATIO:
        return []

    if today_rate < baseline_rate * CONVERSION_CRITICAL_RATIO:
        severity = "CRITICAL"
    else:
        severity = "WARN"

    return [
        Anomaly(
            type="CONVERSION_DROP",
            severity=severity,
            suggested_action=(
                "Review floor staff positioning and zone engagement. "
                "Check for product stockouts in high-dwell zones."
            ),
            detected_at=datetime.now(timezone.utc).isoformat(),
            details={
                "today_rate": round(today_rate, 4),
                "baseline_avg_7d": round(baseline_rate, 4),
                "ratio": round(today_rate / baseline_rate, 2) if baseline_rate else 0,
            },
        )
    ]


# ---------------------------------------------------------------------------
# DEAD_ZONE
# ---------------------------------------------------------------------------

def _check_dead_zones(
    store_id: str, now: datetime, db: Session
) -> List[Anomaly]:
    """
    Flag zones that have had traffic in the past but no ZONE_ENTER in the
    last DEAD_ZONE_WINDOW_MINUTES minutes.

    Only fires when the store has had ANY recent activity
    (prevents false alerts when the store is legitimately closed or quiet).
    """
    rows = db.execute(
        text("""
            WITH store_active AS (
                -- Is the store actively generating events right now?
                -- Uses integer multiplication to avoid INTERVAL string injection.
                SELECT COUNT(*) > 0 AS is_active
                FROM events
                WHERE store_id  = :store_id
                  AND timestamp > NOW() - (:active_mins * INTERVAL '1 minute')
            ),
            known_zones AS (
                SELECT DISTINCT zone_id
                FROM events
                WHERE store_id   = :store_id
                  AND zone_id IS NOT NULL
                  AND event_type = 'ZONE_ENTER'
            ),
            recent_zones AS (
                SELECT DISTINCT zone_id
                FROM events
                WHERE store_id   = :store_id
                  AND event_type = 'ZONE_ENTER'
                  AND timestamp  > NOW() - (:window_mins * INTERVAL '1 minute')
            )
            SELECT kz.zone_id
            FROM known_zones kz
            LEFT JOIN recent_zones rz ON kz.zone_id = rz.zone_id
            CROSS JOIN store_active sa
            WHERE rz.zone_id IS NULL
              AND sa.is_active = true
            ORDER BY kz.zone_id
        """),
        {
            "store_id": store_id,
            "active_mins": STORE_ACTIVE_WINDOW_MINUTES,
            "window_mins": DEAD_ZONE_WINDOW_MINUTES,
        },
    ).fetchall()

    if not rows:
        return []

    dead_zone_ids = [row.zone_id for row in rows]
    severity = "WARN" if len(dead_zone_ids) > 2 else "INFO"

    return [
        Anomaly(
            type="DEAD_ZONE",
            severity=severity,
            suggested_action=(
                f"Check camera feed for {dead_zone_ids}. "
                "Verify display setup and staff coverage in those zones."
            ),
            detected_at=now.isoformat(),
            details={
                "dead_zones": dead_zone_ids,
                "window_minutes": DEAD_ZONE_WINDOW_MINUTES,
                "zone_count": len(dead_zone_ids),
            },
        )
    ]
