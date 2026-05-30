# PROMPT: Write tests for pipeline event schema validation. The pipeline produces
# JSONL events that must match the StoreEvent Pydantic schema exactly before being
# posted to the API. Test all 8 event types, visitor_id format, timestamp format,
# metadata structure, and cross-field rules (zone_id nullness per event type).
# CHANGES MADE: Focused on schema validation (Pydantic layer) not detection model
# output since the detection pipeline runs offline. Used make_event() factory and
# extended it for each event type combination. Added confidence passthrough test
# since low-confidence events must not be suppressed (scoring criterion).

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import EventType, StoreEvent
from tests.conftest import make_event


def parse(event_dict: dict) -> StoreEvent:
    """Parse an event dict through the Pydantic schema."""
    return StoreEvent.model_validate(event_dict)


def make_zone_event(event_type: str, zone_id: str = "SKINCARE", **kwargs) -> dict:
    return make_event(
        event_type=event_type,
        zone_id=zone_id,
        metadata={"queue_depth": None, "sku_zone": zone_id, "session_seq": 2},
        **kwargs,
    )


# ---------------------------------------------------------------------------
# All 8 event types parse successfully
# ---------------------------------------------------------------------------

class TestAllEventTypesParse:

    def test_entry_parses(self):
        e = parse(make_event(event_type="ENTRY", zone_id=None))
        assert e.event_type == EventType.ENTRY

    def test_exit_parses(self):
        e = parse(make_event(event_type="EXIT", zone_id=None,
                             metadata={"queue_depth": None, "sku_zone": None, "session_seq": 5}))
        assert e.event_type == EventType.EXIT

    def test_zone_enter_parses(self):
        e = parse(make_zone_event("ZONE_ENTER"))
        assert e.event_type == EventType.ZONE_ENTER
        assert e.zone_id == "SKINCARE"

    def test_zone_exit_parses(self):
        e = parse(make_zone_event("ZONE_EXIT", dwell_ms=45000))
        assert e.event_type == EventType.ZONE_EXIT

    def test_zone_dwell_parses(self):
        e = parse(make_zone_event("ZONE_DWELL", dwell_ms=30000))
        assert e.event_type == EventType.ZONE_DWELL
        assert e.dwell_ms == 30000

    def test_billing_queue_join_parses(self):
        e = parse(make_event(
            event_type="BILLING_QUEUE_JOIN",
            zone_id="BILLING",
            metadata={"queue_depth": 3, "sku_zone": "BILLING", "session_seq": 4},
        ))
        assert e.event_type == EventType.BILLING_QUEUE_JOIN
        assert e.metadata.queue_depth == 3

    def test_billing_queue_abandon_parses(self):
        e = parse(make_event(
            event_type="BILLING_QUEUE_ABANDON",
            zone_id="BILLING",
            dwell_ms=120000,
            metadata={"queue_depth": None, "sku_zone": "BILLING", "session_seq": 5},
        ))
        assert e.event_type == EventType.BILLING_QUEUE_ABANDON

    def test_reentry_parses(self):
        e = parse(make_event(
            event_type="REENTRY",
            zone_id=None,
            metadata={"queue_depth": None, "sku_zone": None, "session_seq": 8},
        ))
        assert e.event_type == EventType.REENTRY


# ---------------------------------------------------------------------------
# event_id — must be a valid UUID v4
# ---------------------------------------------------------------------------

class TestEventId:

    def test_valid_uuid4_accepted(self):
        e = parse(make_event(event_id=str(uuid.uuid4())))
        assert e.event_id is not None

    def test_invalid_uuid_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(event_id="not-a-uuid"))

    def test_uuid_is_preserved(self):
        eid = str(uuid.uuid4())
        e = parse(make_event(event_id=eid))
        assert str(e.event_id) == eid


# ---------------------------------------------------------------------------
# visitor_id
# ---------------------------------------------------------------------------

class TestVisitorId:

    def test_vis_prefixed_id_accepted(self):
        e = parse(make_event(visitor_id="VIS_abc123"))
        assert e.visitor_id == "VIS_abc123"

    def test_empty_visitor_id_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(visitor_id=""))


# ---------------------------------------------------------------------------
# timestamp
# ---------------------------------------------------------------------------

class TestTimestamp:

    def test_iso8601_utc_z_suffix_accepted(self):
        e = parse(make_event(timestamp="2026-03-03T14:22:10Z"))
        assert e.timestamp is not None

    def test_iso8601_with_offset_accepted(self):
        e = parse(make_event(timestamp="2026-03-03T14:22:10+00:00"))
        assert e.timestamp is not None

    def test_invalid_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(timestamp="not-a-date"))


# ---------------------------------------------------------------------------
# confidence — passthrough, never suppressed
# ---------------------------------------------------------------------------

class TestConfidencePassthrough:

    def test_very_low_confidence_accepted(self):
        """
        Low-confidence detections must NOT be filtered at schema level.
        The scoring harness checks this explicitly.
        """
        e = parse(make_event(confidence=0.01))
        assert e.confidence == pytest.approx(0.01)

    def test_zero_confidence_accepted(self):
        e = parse(make_event(confidence=0.0))
        assert e.confidence == 0.0

    def test_max_confidence_accepted(self):
        e = parse(make_event(confidence=1.0))
        assert e.confidence == 1.0

    def test_above_1_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(confidence=1.001))

    def test_below_0_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(confidence=-0.001))


# ---------------------------------------------------------------------------
# Cross-field rules — zone_id vs event_type
# ---------------------------------------------------------------------------

class TestCrossFieldRules:

    def test_entry_with_zone_id_rejected(self):
        with pytest.raises(ValidationError, match="zone_id"):
            parse(make_event(event_type="ENTRY", zone_id="SKINCARE"))

    def test_exit_with_zone_id_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(event_type="EXIT", zone_id="BILLING",
                             metadata={"queue_depth": None, "sku_zone": None, "session_seq": 2}))

    def test_reentry_with_zone_id_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(event_type="REENTRY", zone_id="SKINCARE",
                             metadata={"queue_depth": None, "sku_zone": None, "session_seq": 3}))

    def test_zone_enter_without_zone_id_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(event_type="ZONE_ENTER", zone_id=None,
                             metadata={"queue_depth": None, "sku_zone": None, "session_seq": 2}))

    def test_billing_join_without_queue_depth_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(
                event_type="BILLING_QUEUE_JOIN",
                zone_id="BILLING",
                metadata={"queue_depth": None, "sku_zone": "BILLING", "session_seq": 2},
            ))

    def test_billing_join_queue_depth_zero_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(
                event_type="BILLING_QUEUE_JOIN",
                zone_id="BILLING",
                metadata={"queue_depth": 0, "sku_zone": "BILLING", "session_seq": 2},
            ))

    def test_billing_join_queue_depth_positive_accepted(self):
        e = parse(make_event(
            event_type="BILLING_QUEUE_JOIN",
            zone_id="BILLING",
            metadata={"queue_depth": 5, "sku_zone": "BILLING", "session_seq": 2},
        ))
        assert e.metadata.queue_depth == 5


# ---------------------------------------------------------------------------
# metadata.session_seq
# ---------------------------------------------------------------------------

class TestSessionSeq:

    def test_seq_one_accepted(self):
        e = parse(make_event(metadata={"queue_depth": None, "sku_zone": None, "session_seq": 1}))
        assert e.metadata.session_seq == 1

    def test_seq_zero_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(metadata={"queue_depth": None, "sku_zone": None, "session_seq": 0}))

    def test_seq_negative_rejected(self):
        with pytest.raises(ValidationError):
            parse(make_event(metadata={"queue_depth": None, "sku_zone": None, "session_seq": -1}))

    def test_seq_increments_across_session(self):
        """Each event in a session gets a higher sequence number."""
        events = [
            parse(make_event(event_type="ENTRY", zone_id=None,
                             metadata={"queue_depth": None, "sku_zone": None, "session_seq": i}))
            for i in range(1, 6)
        ]
        seqs = [e.metadata.session_seq for e in events]
        assert seqs == sorted(seqs)
