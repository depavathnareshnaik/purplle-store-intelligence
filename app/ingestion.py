"""
Event ingestion pipeline.

Responsibilities:
  1. Validate each raw event against StoreEvent schema (per-event, not per-batch)
  2. Bulk-insert valid events — idempotent via ON CONFLICT (event_id) DO NOTHING
  3. Reconstruct sessions from ENTRY / EXIT / ZONE_ENTER / BILLING_QUEUE_JOIN events
  4. Return a partial-success response: accepted count + per-rejected-event errors
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, List

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Event, VisitorSession
from app.schemas import EventType, IngestError, IngestResponse, StoreEvent

logger = logging.getLogger("api.ingestion")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_ingest(raw_events: List[Any], db: Session) -> IngestResponse:
    """
    Validate, deduplicate, store, and reconstruct sessions for a raw event batch.

    Always returns IngestResponse — never raises.  Callers can inspect
    .rejected and .errors to understand what was dropped and why.
    """
    accepted: List[StoreEvent] = []
    errors: List[IngestError] = []

    for raw in raw_events:
        event_id = _extract_event_id(raw)
        try:
            validated = StoreEvent.model_validate(raw)
            accepted.append(validated)
        except (ValidationError, Exception) as exc:
            errors.append(
                IngestError(event_id=event_id, reason=_format_error(exc))
            )

    if accepted:
        _bulk_insert_events(db, accepted)
        _reconstruct_sessions(db, accepted)
        db.commit()

    logger.info(
        '{"message": "ingest complete", "accepted": %d, "rejected": %d}',
        len(accepted),
        len(errors),
    )

    return IngestResponse(
        accepted=len(accepted),
        rejected=len(errors),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Step 1 — Bulk insert
# ---------------------------------------------------------------------------

def _bulk_insert_events(db: Session, events: List[StoreEvent]) -> None:
    """
    Insert all validated events in a single round-trip.
    ON CONFLICT DO NOTHING makes this idempotent — the same event_id
    posted a second time is silently ignored without raising an error.
    """
    rows = [_to_row(e) for e in events]
    db.execute(
        pg_insert(Event)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["event_id"])
    )


def _to_row(event: StoreEvent) -> dict:
    """Flatten StoreEvent (including nested metadata) into a DB-ready dict."""
    return {
        "event_id": event.event_id,
        "store_id": event.store_id,
        "camera_id": event.camera_id,
        "visitor_id": event.visitor_id,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp,
        "zone_id": event.zone_id,
        "dwell_ms": event.dwell_ms,
        "is_staff": event.is_staff,
        "confidence": event.confidence,
        "queue_depth": event.metadata.queue_depth,
        "sku_zone": event.metadata.sku_zone,
        "session_seq": event.metadata.session_seq,
    }


# ---------------------------------------------------------------------------
# Step 2 — Session reconstruction
# ---------------------------------------------------------------------------

def _reconstruct_sessions(db: Session, events: List[StoreEvent]) -> None:
    """
    Keep the sessions table in sync with the events table.

    Sessions are the unit of analysis for the funnel and conversion rate.
    This runs inside the same transaction as the event insert, so either
    both commit or neither does.
    """
    for event in events:
        if event.event_type == EventType.ENTRY:
            _session_open(db, event)
        elif event.event_type == EventType.REENTRY:
            # REENTRY opens a new session row with the same visitor_id.
            # This lets subsequent ZONE_ENTER events find an open session.
            # The funnel uses COUNT(DISTINCT visitor_id) so the visitor is
            # still counted once regardless of how many sessions they have.
            _session_open(db, event)
        elif event.event_type == EventType.EXIT:
            _session_close(db, event)
        elif event.event_type == EventType.ZONE_ENTER:
            _session_add_zone(db, event)
        elif event.event_type == EventType.BILLING_QUEUE_JOIN:
            _session_mark_billing(db, event)
        # ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_ABANDON
        # do not change the session structure — handled at query time in metrics


def _session_open(db: Session, event: StoreEvent) -> None:
    """
    Create a new session row when a visitor enters the store.

    The UNIQUE constraint on (visitor_id, store_id, entry_time) makes this
    idempotent — ingesting the same ENTRY event twice creates only one row.
    """
    db.execute(
        pg_insert(VisitorSession)
        .values(
            session_id=uuid.uuid4(),
            store_id=event.store_id,
            visitor_id=event.visitor_id,
            entry_time=event.timestamp,
            is_staff=event.is_staff,
            session_date=event.timestamp.date(),
        )
        .on_conflict_do_nothing(
            index_elements=["visitor_id", "store_id", "entry_time"]
        )
    )


def _session_close(db: Session, event: StoreEvent) -> None:
    """
    Stamp exit_time on the most recent open session for this visitor.
    A session is 'open' when exit_time IS NULL.
    """
    db.execute(
        text("""
            UPDATE sessions
            SET exit_time = :exit_time
            WHERE session_id = (
                SELECT session_id
                FROM sessions
                WHERE visitor_id = :visitor_id
                  AND store_id   = :store_id
                  AND exit_time IS NULL
                ORDER BY entry_time DESC
                LIMIT 1
            )
        """),
        {
            "exit_time": event.timestamp,
            "visitor_id": event.visitor_id,
            "store_id": event.store_id,
        },
    )


def _session_add_zone(db: Session, event: StoreEvent) -> None:
    """
    Append the entered zone to visited_zones, avoiding duplicates.
    NOT (:zone_id = ANY(visited_zones)) ensures idempotency.
    """
    db.execute(
        text("""
            UPDATE sessions
            SET visited_zones = array_append(visited_zones, :zone_id)
            WHERE session_id = (
                SELECT session_id
                FROM sessions
                WHERE visitor_id = :visitor_id
                  AND store_id   = :store_id
                  AND exit_time IS NULL
                ORDER BY entry_time DESC
                LIMIT 1
            )
              AND NOT (:zone_id = ANY(visited_zones))
        """),
        {
            "zone_id": event.zone_id,
            "visitor_id": event.visitor_id,
            "store_id": event.store_id,
        },
    )


def _session_mark_billing(db: Session, event: StoreEvent) -> None:
    """Mark that this visitor reached the billing zone in their current session."""
    db.execute(
        text("""
            UPDATE sessions
            SET reached_billing = true
            WHERE session_id = (
                SELECT session_id
                FROM sessions
                WHERE visitor_id = :visitor_id
                  AND store_id   = :store_id
                  AND exit_time IS NULL
                ORDER BY entry_time DESC
                LIMIT 1
            )
        """),
        {"visitor_id": event.visitor_id, "store_id": event.store_id},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_event_id(raw: Any) -> str:
    """
    Pull event_id out of whatever the caller sent — may be missing or malformed.
    Returns a placeholder string so the error response always has an event_id field.
    """
    if isinstance(raw, dict):
        return str(raw.get("event_id", "unknown"))
    return "unknown"


def _format_error(exc: Exception) -> str:
    """Produce a single human-readable string from a Pydantic or generic error."""
    if isinstance(exc, ValidationError):
        # Each Pydantic error: {loc: ('field',), msg: 'reason', ...}
        parts = [
            f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        ]
        return "; ".join(parts)
    return str(exc)
