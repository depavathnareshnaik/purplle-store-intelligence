# PROMPT: Write pytest tests for GET /stores/{id}/funnel focusing on session deduplication.
# Critical requirement: a visitor who re-enters (ENTRY → EXIT → REENTRY) must appear
# exactly once in the funnel entry stage, not twice. Also test drop-off percentages,
# funnel structure (4 stages in order), and edge cases (empty store, staff exclusion).
# CHANGES MADE: Used distinct store IDs per test to prevent cross-test data leakage.
# Asserted stage names and ordering explicitly — order matters for the scoring harness.

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import make_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_funnel(client: TestClient, store_id: str) -> list:
    resp = client.get(f"/stores/{store_id}/funnel")
    assert resp.status_code == 200
    return resp.json()


def ingest(client: TestClient, events: list) -> None:
    resp = client.post("/events/ingest", json=events)
    assert resp.status_code == 200


def stage(funnel: list, stage_name: str) -> dict:
    """Get a stage by name from the funnel list."""
    for s in funnel:
        if s["stage"] == stage_name:
            return s
    raise AssertionError(f"Stage '{stage_name}' not found in funnel: {funnel}")


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

class TestFunnelStructure:

    def test_four_stages_returned(self, client, db_session):
        funnel = get_funnel(client, "STORE_FUNNEL_STR")
        assert len(funnel) == 4

    def test_stage_names_correct_and_ordered(self, client, db_session):
        funnel = get_funnel(client, "STORE_FUNNEL_ORD")
        names = [s["stage"] for s in funnel]
        assert names == ["entry", "zone_visit", "billing_queue", "purchase"]

    def test_each_stage_has_required_fields(self, client, db_session):
        funnel = get_funnel(client, "STORE_FUNNEL_FLD")
        for s in funnel:
            assert "stage" in s
            assert "count" in s
            assert "drop_off_pct" in s
            assert isinstance(s["count"], int)
            assert isinstance(s["drop_off_pct"], float)

    def test_entry_stage_drop_off_is_zero(self, client, db_session):
        funnel = get_funnel(client, "STORE_FUNNEL_DRP")
        entry = stage(funnel, "entry")
        assert entry["drop_off_pct"] == 0.0

    def test_stage_counts_are_non_negative(self, client, db_session):
        funnel = get_funnel(client, "STORE_FUNNEL_NEG")
        for s in funnel:
            assert s["count"] >= 0

    def test_counts_decrease_monotonically(self, client, db_session):
        """Each stage count must be ≤ the previous stage count."""
        store_id = "STORE_FUNNEL_MON"
        ingest(client, [
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_ff0001", event_type="ENTRY"),
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_ff0001", event_type="ZONE_ENTER",
                       zone_id="SKINCARE",
                       metadata={"queue_depth": None, "sku_zone": "SKINCARE", "session_seq": 2}),
        ])
        funnel = get_funnel(client, store_id)
        counts = [s["count"] for s in funnel]
        for i in range(1, len(counts)):
            assert counts[i] <= counts[i - 1], (
                f"Stage {funnel[i]['stage']} count {counts[i]} exceeds "
                f"previous stage {funnel[i-1]['stage']} count {counts[i-1]}"
            )


# ---------------------------------------------------------------------------
# Empty store
# ---------------------------------------------------------------------------

class TestFunnelEmptyStore:

    def test_empty_store_all_zeros(self, client, db_session):
        funnel = get_funnel(client, "STORE_FUNNEL_EMPTY_999")
        for s in funnel:
            assert s["count"] == 0
        assert stage(funnel, "entry")["drop_off_pct"] == 0.0

    def test_empty_store_status_200(self, client, db_session):
        resp = client.get("/stores/STORE_NO_EXIST_FUNNEL/funnel")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Re-entry deduplication — critical scoring criterion
# ---------------------------------------------------------------------------

class TestFunnelReentryDeduplication:

    def test_reentry_visitor_counted_once_in_entry_stage(self, client, db_session):
        """
        A visitor who exits and re-enters must appear exactly ONCE in the funnel
        entry stage — not twice. This is the key deduplication requirement.
        """
        store_id = "STORE_REENTRY_DEDUP"
        visitor = "VIS_re0001"

        ingest(client, [
            # First visit
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id=visitor, event_type="ENTRY"),
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id=visitor, event_type="EXIT",
                       metadata={"queue_depth": None, "sku_zone": None, "session_seq": 2}),
            # Re-entry (same person)
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id=visitor, event_type="REENTRY",
                       metadata={"queue_depth": None, "sku_zone": None, "session_seq": 3}),
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id=visitor, event_type="EXIT",
                       metadata={"queue_depth": None, "sku_zone": None, "session_seq": 4}),
        ])

        funnel = get_funnel(client, store_id)
        entry = stage(funnel, "entry")
        assert entry["count"] == 1, (
            f"Expected 1 unique visitor, got {entry['count']}. "
            "Re-entry should not double-count the visitor."
        )

    def test_two_different_visitors_count_as_two(self, client, db_session):
        store_id = "STORE_TWO_VISITORS"
        ingest(client, [
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_two001", event_type="ENTRY"),
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_two002", event_type="ENTRY"),
        ])

        funnel = get_funnel(client, store_id)
        assert stage(funnel, "entry")["count"] == 2


# ---------------------------------------------------------------------------
# Stage progression
# ---------------------------------------------------------------------------

class TestFunnelStageProgression:

    def test_zone_visit_stage_populated_after_zone_enter(self, client, db_session):
        store_id = "STORE_FUNNEL_ZONE"
        ingest(client, [
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_zz0001", event_type="ENTRY"),
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_zz0001", event_type="ZONE_ENTER",
                       zone_id="SKINCARE",
                       metadata={"queue_depth": None, "sku_zone": "SKINCARE", "session_seq": 2}),
        ])

        funnel = get_funnel(client, store_id)
        assert stage(funnel, "zone_visit")["count"] >= 1

    def test_billing_stage_populated_after_billing_queue_join(self, client, db_session):
        store_id = "STORE_FUNNEL_BILL"
        ingest(client, [
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_bi0001", event_type="ENTRY"),
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_bi0001", event_type="BILLING_QUEUE_JOIN",
                       zone_id="BILLING",
                       metadata={"queue_depth": 1, "sku_zone": "BILLING", "session_seq": 2}),
        ])

        funnel = get_funnel(client, store_id)
        assert stage(funnel, "billing_queue")["count"] >= 1

    def test_drop_off_percentage_calculated_correctly(self, client, db_session):
        """
        2 enter, 1 visits a zone → zone_visit drop_off = 50%
        """
        store_id = "STORE_FUNNEL_PCT"
        ingest(client, [
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_pct001", event_type="ENTRY"),
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_pct002", event_type="ENTRY"),
            # Only visitor 1 visits a zone
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_pct001", event_type="ZONE_ENTER",
                       zone_id="SKINCARE",
                       metadata={"queue_depth": None, "sku_zone": "SKINCARE", "session_seq": 2}),
        ])

        funnel = get_funnel(client, store_id)
        zone_stage = stage(funnel, "zone_visit")
        # 2 entered, 1 visited → 50% drop off at zone_visit stage
        assert zone_stage["drop_off_pct"] == pytest.approx(50.0, abs=1.0)


# ---------------------------------------------------------------------------
# Staff exclusion
# ---------------------------------------------------------------------------

class TestFunnelStaffExclusion:

    def test_staff_not_counted_in_entry_stage(self, client, db_session):
        store_id = "STORE_FUNNEL_STAFF"
        ingest(client, [
            make_event(event_id=str(uuid.uuid4()), store_id=store_id,
                       visitor_id="VIS_sf0001", event_type="ENTRY", is_staff=True),
        ])

        funnel = get_funnel(client, store_id)
        assert stage(funnel, "entry")["count"] == 0
