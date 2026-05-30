# PROMPT: Write pytest tests for POST /events/ingest with these requirements:
#   - Idempotent: same event_id posted twice must not create duplicate DB rows
#   - Partial success: valid + malformed in same batch → accepted + rejected counts
#   - Never 5xx on malformed input — always HTTP 200 with structured errors list
#   - Validate all 8 event types, confidence bounds, zone_id rules, queue_depth rules
#   - Edge cases: empty batch, batch > 500, all-staff clip, missing required fields
# CHANGES MADE: Used make_event() factory from conftest for DRY setup.
# Asserted response schema fields explicitly, not just status codes.
# Added DB row-count assertions for idempotency (not just response equality).

import uuid
from typing import List

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import make_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def post_events(client: TestClient, events: list) -> dict:
    resp = client.post("/events/ingest", json=events)
    return resp


def count_events(db: Session, event_ids: List[str]) -> int:
    # Cast event_id to text for reliable comparison regardless of UUID vs text storage
    result = db.execute(
        text("SELECT COUNT(*) FROM events WHERE event_id::text = ANY(:ids)"),
        {"ids": event_ids},
    )
    return result.scalar()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestIngestHappyPath:

    def test_single_valid_event_accepted(self, client, db_session):
        event = make_event()
        resp = post_events(client, [event])

        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 1
        assert body["rejected"] == 0
        assert body["errors"] == []

    def test_batch_of_valid_events_accepted(self, client, db_session):
        events = [make_event(event_id=str(uuid.uuid4()), visitor_id=f"VIS_{i:06x}") for i in range(10)]
        resp = post_events(client, events)

        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 10
        assert body["rejected"] == 0

    def test_empty_batch_returns_zeros(self, client, db_session):
        resp = post_events(client, [])

        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 0
        assert body["rejected"] == 0
        assert body["errors"] == []

    def test_all_eight_event_types_accepted(self, client, db_session):
        visitor = "VIS_aabbcc"
        events = [
            make_event(event_id=str(uuid.uuid4()), event_type="ENTRY",
                       visitor_id=visitor, zone_id=None),
            make_event(event_id=str(uuid.uuid4()), event_type="ZONE_ENTER",
                       visitor_id=visitor, zone_id="SKINCARE",
                       metadata={"queue_depth": None, "sku_zone": "MOISTURISER", "session_seq": 2}),
            make_event(event_id=str(uuid.uuid4()), event_type="ZONE_DWELL",
                       visitor_id=visitor, zone_id="SKINCARE", dwell_ms=30000,
                       metadata={"queue_depth": None, "sku_zone": "MOISTURISER", "session_seq": 3}),
            make_event(event_id=str(uuid.uuid4()), event_type="ZONE_EXIT",
                       visitor_id=visitor, zone_id="SKINCARE", dwell_ms=45000,
                       metadata={"queue_depth": None, "sku_zone": "MOISTURISER", "session_seq": 4}),
            make_event(event_id=str(uuid.uuid4()), event_type="BILLING_QUEUE_JOIN",
                       visitor_id=visitor, zone_id="BILLING",
                       metadata={"queue_depth": 2, "sku_zone": "BILLING", "session_seq": 5}),
            make_event(event_id=str(uuid.uuid4()), event_type="BILLING_QUEUE_ABANDON",
                       visitor_id=visitor, zone_id="BILLING",
                       metadata={"queue_depth": None, "sku_zone": "BILLING", "session_seq": 6}),
            make_event(event_id=str(uuid.uuid4()), event_type="EXIT",
                       visitor_id=visitor, zone_id=None,
                       metadata={"queue_depth": None, "sku_zone": None, "session_seq": 7}),
            make_event(event_id=str(uuid.uuid4()), event_type="REENTRY",
                       visitor_id=visitor, zone_id=None,
                       metadata={"queue_depth": None, "sku_zone": None, "session_seq": 8}),
        ]
        resp = post_events(client, events)

        assert resp.status_code == 200
        assert resp.json()["accepted"] == 8
        assert resp.json()["rejected"] == 0


# ---------------------------------------------------------------------------
# Idempotency — the most critical correctness property
# ---------------------------------------------------------------------------

class TestIdempotency:

    def test_same_event_twice_accepted_once(self, client, db_session):
        event = make_event(event_id=str(uuid.uuid4()))

        resp1 = post_events(client, [event])
        resp2 = post_events(client, [event])

        # Both responses report accepted=1 (the API always says "I accepted it")
        assert resp1.json()["accepted"] == 1
        assert resp2.json()["accepted"] == 1

        # But the DB has exactly ONE row — no duplicate
        row_count = count_events(db_session, [event["event_id"]])
        assert row_count == 1

    def test_same_batch_twice_no_duplicates(self, client, db_session):
        event_ids = [str(uuid.uuid4()) for _ in range(5)]
        events = [make_event(event_id=eid, visitor_id=f"VIS_{i:06x}") for i, eid in enumerate(event_ids)]

        post_events(client, events)
        post_events(client, events)

        row_count = count_events(db_session, event_ids)
        assert row_count == 5  # still 5, not 10


# ---------------------------------------------------------------------------
# Partial success — valid + malformed in the same batch
# ---------------------------------------------------------------------------

class TestPartialSuccess:

    def test_valid_and_malformed_mixed(self, client, db_session):
        good = make_event(event_id=str(uuid.uuid4()))
        bad = {"event_id": "not-a-uuid", "event_type": "ENTRY"}  # missing required fields

        resp = post_events(client, [good, bad])

        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 1
        assert body["rejected"] == 1
        assert len(body["errors"]) == 1
        assert body["errors"][0]["event_id"] == "not-a-uuid"
        assert len(body["errors"][0]["reason"]) > 0

    def test_all_malformed_returns_200_not_5xx(self, client, db_session):
        bad_events = [
            {"garbage": "data"},
            {"event_id": "also-bad"},
            {},
        ]
        resp = post_events(client, bad_events)

        # Must be 200, never 4xx/5xx for malformed event content
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 0
        assert body["rejected"] == 3
        assert len(body["errors"]) == 3

    def test_error_response_has_event_id_and_reason(self, client, db_session):
        bad_event_id = str(uuid.uuid4())
        bad = make_event(event_id=bad_event_id, confidence=99.0)  # confidence > 1.0

        resp = post_events(client, [bad])

        body = resp.json()
        assert body["rejected"] == 1
        error = body["errors"][0]
        assert error["event_id"] == bad_event_id
        assert "confidence" in error["reason"].lower()


# ---------------------------------------------------------------------------
# Schema validation — per-field and cross-field rules
# ---------------------------------------------------------------------------

class TestSchemaValidation:

    def test_confidence_above_1_rejected(self, client, db_session):
        event = make_event(event_id=str(uuid.uuid4()), confidence=1.5)
        resp = post_events(client, [event])
        assert resp.json()["rejected"] == 1

    def test_confidence_below_0_rejected(self, client, db_session):
        event = make_event(event_id=str(uuid.uuid4()), confidence=-0.1)
        resp = post_events(client, [event])
        assert resp.json()["rejected"] == 1

    def test_confidence_at_boundaries_accepted(self, client, db_session):
        events = [
            make_event(event_id=str(uuid.uuid4()), confidence=0.0),
            make_event(event_id=str(uuid.uuid4()), confidence=1.0),
        ]
        resp = post_events(client, events)
        assert resp.json()["accepted"] == 2

    def test_unknown_event_type_rejected(self, client, db_session):
        event = make_event(event_id=str(uuid.uuid4()), event_type="TELEPORT")
        resp = post_events(client, [event])
        assert resp.json()["rejected"] == 1

    def test_entry_with_zone_id_rejected(self, client, db_session):
        # ENTRY events must have zone_id=null
        event = make_event(
            event_id=str(uuid.uuid4()),
            event_type="ENTRY",
            zone_id="SKINCARE",
        )
        resp = post_events(client, [event])
        assert resp.json()["rejected"] == 1

    def test_zone_enter_without_zone_id_rejected(self, client, db_session):
        event = make_event(
            event_id=str(uuid.uuid4()),
            event_type="ZONE_ENTER",
            zone_id=None,
            metadata={"queue_depth": None, "sku_zone": None, "session_seq": 2},
        )
        resp = post_events(client, [event])
        assert resp.json()["rejected"] == 1

    def test_billing_queue_join_without_queue_depth_rejected(self, client, db_session):
        event = make_event(
            event_id=str(uuid.uuid4()),
            event_type="BILLING_QUEUE_JOIN",
            zone_id="BILLING",
            metadata={"queue_depth": None, "sku_zone": "BILLING", "session_seq": 3},
        )
        resp = post_events(client, [event])
        assert resp.json()["rejected"] == 1

    def test_billing_queue_join_with_queue_depth_zero_rejected(self, client, db_session):
        event = make_event(
            event_id=str(uuid.uuid4()),
            event_type="BILLING_QUEUE_JOIN",
            zone_id="BILLING",
            metadata={"queue_depth": 0, "sku_zone": "BILLING", "session_seq": 3},
        )
        resp = post_events(client, [event])
        assert resp.json()["rejected"] == 1

    def test_missing_required_field_rejected(self, client, db_session):
        event = make_event(event_id=str(uuid.uuid4()))
        del event["store_id"]  # required field removed
        resp = post_events(client, [event])
        assert resp.json()["rejected"] == 1

    def test_session_seq_zero_rejected(self, client, db_session):
        event = make_event(
            event_id=str(uuid.uuid4()),
            metadata={"queue_depth": None, "sku_zone": None, "session_seq": 0},
        )
        resp = post_events(client, [event])
        assert resp.json()["rejected"] == 1


# ---------------------------------------------------------------------------
# Edge cases from the problem statement
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_batch_exceeds_500_returns_400(self, client, db_session):
        events = [make_event(event_id=str(uuid.uuid4())) for _ in range(501)]
        resp = post_events(client, events)
        assert resp.status_code == 400

    def test_staff_events_stored_with_is_staff_true(self, client, db_session):
        staff_event_id = str(uuid.uuid4())
        event = make_event(event_id=staff_event_id, is_staff=True)

        resp = post_events(client, [event])
        assert resp.json()["accepted"] == 1

        row = db_session.execute(
            text("SELECT is_staff FROM events WHERE event_id = :eid"),
            {"eid": staff_event_id},
        ).fetchone()
        assert row is not None
        assert row.is_staff is True

    def test_low_confidence_event_accepted_not_suppressed(self, client, db_session):
        # Confidence passthrough is a scoring criterion — low-conf events must NOT be dropped
        event = make_event(event_id=str(uuid.uuid4()), confidence=0.05)
        resp = post_events(client, [event])
        assert resp.json()["accepted"] == 1

    def test_dwell_ms_zero_accepted_for_instantaneous_events(self, client, db_session):
        event = make_event(event_id=str(uuid.uuid4()), event_type="ENTRY", dwell_ms=0)
        resp = post_events(client, [event])
        assert resp.json()["accepted"] == 1

    def test_reentry_event_accepted(self, client, db_session):
        event = make_event(
            event_id=str(uuid.uuid4()),
            event_type="REENTRY",
            zone_id=None,
            metadata={"queue_depth": None, "sku_zone": None, "session_seq": 5},
        )
        resp = post_events(client, [event])
        assert resp.json()["accepted"] == 1
