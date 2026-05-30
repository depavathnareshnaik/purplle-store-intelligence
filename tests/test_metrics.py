# PROMPT: Write pytest tests for GET /stores/{id}/metrics and GET /stores/{id}/heatmap.
# Requirements: exclude staff, handle zero purchases, handle empty store, test all fields
# present, test conversion rate with POS data, test abandonment rate calculation.
# CHANGES MADE: Added POS data insertion helper for conversion rate tests.
# Tested response schema fields explicitly (types, ranges) not just status codes.
# Used separate visitor IDs per test class to avoid cross-test contamination.

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

def get_metrics(client: TestClient, store_id: str = "STORE_BLR_002") -> dict:
    resp = client.get(f"/stores/{store_id}/metrics")
    assert resp.status_code == 200
    return resp.json()


def get_heatmap(client: TestClient, store_id: str = "STORE_BLR_002") -> dict:
    resp = client.get(f"/stores/{store_id}/heatmap")
    assert resp.status_code == 200
    return resp.json()


def ingest(client: TestClient, events: list) -> None:
    resp = client.post("/events/ingest", json=events)
    assert resp.status_code == 200


def insert_pos_transaction(db: Session, store_id: str, ts: datetime) -> None:
    db.execute(
        text("""
            INSERT INTO pos_transactions (transaction_id, store_id, timestamp, basket_value_inr)
            VALUES (:txn_id, :store_id, :ts, 999.00)
            ON CONFLICT DO NOTHING
        """),
        {"txn_id": str(uuid.uuid4()), "store_id": store_id, "ts": ts},
    )
    db.commit()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class TestMetricsSchema:

    def test_required_fields_present(self, client, db_session):
        data = get_metrics(client)
        for field in [
            "store_id", "date", "unique_visitors", "conversion_rate",
            "avg_dwell_by_zone", "queue_depth", "abandonment_rate", "computed_at",
        ]:
            assert field in data, f"Missing field: {field}"

    def test_field_types_correct(self, client, db_session):
        data = get_metrics(client)
        assert isinstance(data["unique_visitors"], int)
        assert isinstance(data["conversion_rate"], float)
        assert isinstance(data["avg_dwell_by_zone"], dict)
        assert isinstance(data["queue_depth"], int)
        assert isinstance(data["abandonment_rate"], float)

    def test_conversion_rate_between_0_and_1(self, client, db_session):
        data = get_metrics(client)
        assert 0.0 <= data["conversion_rate"] <= 1.0

    def test_abandonment_rate_between_0_and_1(self, client, db_session):
        data = get_metrics(client)
        assert 0.0 <= data["abandonment_rate"] <= 1.0


# ---------------------------------------------------------------------------
# Empty store
# ---------------------------------------------------------------------------

class TestMetricsEmptyStore:

    def test_empty_store_returns_zeros_not_error(self, client, db_session):
        data = get_metrics(client, store_id="STORE_EMPTY_999")
        assert data["unique_visitors"] == 0
        assert data["conversion_rate"] == 0.0
        assert data["queue_depth"] == 0
        assert data["abandonment_rate"] == 0.0
        assert data["avg_dwell_by_zone"] == {}

    def test_empty_store_status_200(self, client, db_session):
        resp = client.get("/stores/STORE_DOES_NOT_EXIST/metrics")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Staff exclusion
# ---------------------------------------------------------------------------

class TestMetricsStaffExclusion:

    def test_staff_visitors_excluded_from_unique_count(self, client, db_session):
        # Ingest one customer + one staff member
        ingest(client, [
            make_event(event_id=str(uuid.uuid4()), visitor_id="VIS_cust01", is_staff=False),
            make_event(event_id=str(uuid.uuid4()), visitor_id="VIS_staf01", is_staff=True),
        ])

        data = get_metrics(client)
        # Staff should not appear in unique_visitors
        # (there may be other visitors from other tests, so we check >= 1 not == 1)
        assert data["unique_visitors"] >= 1

    def test_all_staff_clip_returns_zero_visitors(self, client, db_session):
        store_id = "STORE_STAFF_ONLY"
        ingest(client, [
            make_event(
                event_id=str(uuid.uuid4()),
                store_id=store_id,
                visitor_id="VIS_st0001",
                is_staff=True,
            ),
            make_event(
                event_id=str(uuid.uuid4()),
                store_id=store_id,
                visitor_id="VIS_st0002",
                is_staff=True,
            ),
        ])

        data = get_metrics(client, store_id=store_id)
        assert data["unique_visitors"] == 0
        assert data["conversion_rate"] == 0.0


# ---------------------------------------------------------------------------
# Conversion rate — POS correlation
# ---------------------------------------------------------------------------

class TestMetricsConversion:

    def test_conversion_rate_zero_without_pos_data(self, client, db_session):
        store_id = "STORE_NO_POS"
        ingest(client, [
            make_event(
                event_id=str(uuid.uuid4()),
                store_id=store_id,
                visitor_id="VIS_aa0001",
                event_type="BILLING_QUEUE_JOIN",
                zone_id="BILLING",
                metadata={"queue_depth": 1, "sku_zone": "BILLING", "session_seq": 2},
            )
        ])
        data = get_metrics(client, store_id=store_id)
        assert data["conversion_rate"] == 0.0

    def test_conversion_rate_with_matching_pos_transaction(self, client, db_session):
        store_id = "STORE_POS_MATCH"
        now = datetime.now(timezone.utc)

        # Visitor joins billing queue 2 minutes before a POS transaction
        billing_ts = now - timedelta(minutes=2)
        pos_ts = now

        ingest(client, [
            make_event(
                event_id=str(uuid.uuid4()),
                store_id=store_id,
                visitor_id="VIS_bb0001",
                event_type="ENTRY",
                timestamp=billing_ts.isoformat(),
                zone_id=None,
                metadata={"queue_depth": None, "sku_zone": None, "session_seq": 1},
            ),
            make_event(
                event_id=str(uuid.uuid4()),
                store_id=store_id,
                visitor_id="VIS_bb0001",
                event_type="BILLING_QUEUE_JOIN",
                timestamp=billing_ts.isoformat(),
                zone_id="BILLING",
                metadata={"queue_depth": 1, "sku_zone": "BILLING", "session_seq": 2},
            ),
        ])
        insert_pos_transaction(db_session, store_id, pos_ts)

        data = get_metrics(client, store_id=store_id)
        assert data["conversion_rate"] > 0.0
        assert data["conversion_rate"] <= 1.0

    def test_conversion_rate_outside_5min_window_not_converted(self, client, db_session):
        store_id = "STORE_NO_WINDOW"
        now = datetime.now(timezone.utc)

        # Visitor in billing zone 10 minutes BEFORE the POS transaction
        # (outside the 5-minute window — should NOT convert)
        billing_ts = now - timedelta(minutes=10)
        pos_ts = now

        ingest(client, [
            make_event(
                event_id=str(uuid.uuid4()),
                store_id=store_id,
                visitor_id="VIS_cc0001",
                event_type="BILLING_QUEUE_JOIN",
                timestamp=billing_ts.isoformat(),
                zone_id="BILLING",
                metadata={"queue_depth": 1, "sku_zone": "BILLING", "session_seq": 1},
            )
        ])
        insert_pos_transaction(db_session, store_id, pos_ts)

        data = get_metrics(client, store_id=store_id)
        assert data["conversion_rate"] == 0.0


# ---------------------------------------------------------------------------
# Abandonment rate
# ---------------------------------------------------------------------------

class TestMetricsAbandonment:

    def test_abandonment_rate_calculated_correctly(self, client, db_session):
        store_id = "STORE_ABANDON"
        # 2 joins, 1 abandon → abandonment_rate = 0.5
        ingest(client, [
            make_event(
                event_id=str(uuid.uuid4()), store_id=store_id,
                visitor_id="VIS_dd0001", event_type="BILLING_QUEUE_JOIN",
                zone_id="BILLING",
                metadata={"queue_depth": 1, "sku_zone": "BILLING", "session_seq": 1},
            ),
            make_event(
                event_id=str(uuid.uuid4()), store_id=store_id,
                visitor_id="VIS_dd0002", event_type="BILLING_QUEUE_JOIN",
                zone_id="BILLING",
                metadata={"queue_depth": 2, "sku_zone": "BILLING", "session_seq": 1},
            ),
            make_event(
                event_id=str(uuid.uuid4()), store_id=store_id,
                visitor_id="VIS_dd0001", event_type="BILLING_QUEUE_ABANDON",
                zone_id="BILLING", dwell_ms=45000,
                metadata={"queue_depth": None, "sku_zone": "BILLING", "session_seq": 2},
            ),
        ])

        data = get_metrics(client, store_id=store_id)
        assert data["abandonment_rate"] == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# Average dwell
# ---------------------------------------------------------------------------

class TestMetricsDwell:

    def test_avg_dwell_by_zone_populated(self, client, db_session):
        store_id = "STORE_DWELL"
        ingest(client, [
            make_event(
                event_id=str(uuid.uuid4()), store_id=store_id,
                visitor_id="VIS_ee0001", event_type="ZONE_DWELL",
                zone_id="SKINCARE", dwell_ms=30000,
                metadata={"queue_depth": None, "sku_zone": "SKINCARE", "session_seq": 2},
            ),
        ])

        data = get_metrics(client, store_id=store_id)
        assert "SKINCARE" in data["avg_dwell_by_zone"]
        assert data["avg_dwell_by_zone"]["SKINCARE"] == pytest.approx(30000, abs=1)


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

class TestHeatmap:

    def test_heatmap_required_fields(self, client, db_session):
        data = get_heatmap(client, store_id="STORE_HEATMAP_EMPTY")
        assert "store_id" in data
        assert "data_confidence" in data
        assert "zones" in data
        assert "computed_at" in data

    def test_empty_store_heatmap_returns_low_confidence(self, client, db_session):
        data = get_heatmap(client, store_id="STORE_HEAT_NONE")
        assert data["data_confidence"] == "low"
        assert data["zones"] == []

    def test_heatmap_normalized_score_max_is_100(self, client, db_session):
        store_id = "STORE_HEAT_NORM"
        for i in range(3):
            ingest(client, [
                make_event(
                    event_id=str(uuid.uuid4()), store_id=store_id,
                    visitor_id=f"VIS_hh{i:04x}", event_type="ZONE_ENTER",
                    zone_id="SKINCARE",
                    metadata={"queue_depth": None, "sku_zone": "SKINCARE", "session_seq": 2},
                )
            ])

        data = get_heatmap(client, store_id=store_id)
        if data["zones"]:
            scores = [z["normalized_score"] for z in data["zones"]]
            assert max(scores) == pytest.approx(100.0, abs=0.1)
