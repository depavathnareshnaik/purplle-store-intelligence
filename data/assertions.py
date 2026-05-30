#!/usr/bin/env python3
"""
assertions.py — 10 API acceptance assertions for Store Intelligence.

This is the scoring harness test file. Run it against the live API:

  docker compose up --build -d
  python scripts/generate_dataset.py
  python scripts/ingest_events.py
  python data/assertions.py

All 10 assertions must pass for full Part B scoring.
"""

import sys
import uuid

import httpx

BASE     = "http://localhost:8000"
STORE_ID = "STORE_BLR_002"
PASSED   = 0
FAILED   = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ✓  {name}")
    else:
        FAILED += 1
        print(f"  ✗  {name}")
        if detail:
            print(f"       {detail}")


def make_event(**overrides) -> dict:
    base = {
        "event_id":  str(uuid.uuid4()),
        "store_id":  STORE_ID,
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": f"VIS_{uuid.uuid4().hex[:6]}",
        "event_type": "ENTRY",
        "timestamp":  "2026-03-03T14:22:10Z",
        "zone_id":    None,
        "dwell_ms":   0,
        "is_staff":   False,
        "confidence": 0.91,
        "metadata":   {"queue_depth": None, "sku_zone": None, "session_seq": 1},
    }
    base.update(overrides)
    return base


print(f"\n{'='*58}")
print("  Store Intelligence — Acceptance Assertions")
print(f"{'='*58}\n")

# ── 1. Health endpoint returns 200 with correct structure ─────────────────────
r = httpx.get(f"{BASE}/health")
body = r.json()
check(
    "Health returns 200 with required fields",
    r.status_code == 200
    and "status" in body
    and "database" in body
    and "stores" in body,
    f"got status={r.status_code} body={body}",
)

# ── 2. POST /events/ingest accepts valid events ───────────────────────────────
event = make_event()
r = httpx.post(f"{BASE}/events/ingest", json=[event])
body = r.json()
check(
    "Ingest accepts valid events (no 5xx)",
    r.status_code == 200 and body.get("accepted", 0) >= 1 and body.get("rejected", 0) == 0,
    f"got {body}",
)

# ── 3. POST /events/ingest is idempotent ──────────────────────────────────────
event2 = make_event()
r1 = httpx.post(f"{BASE}/events/ingest", json=[event2])
r2 = httpx.post(f"{BASE}/events/ingest", json=[event2])   # exact same payload
check(
    "Ingest is idempotent (same event_id posted twice)",
    r1.status_code == 200
    and r2.status_code == 200
    and r1.json().get("accepted") == r2.json().get("accepted"),
    f"r1={r1.json()} r2={r2.json()}",
)

# ── 4. Malformed events return 200 with structured errors ─────────────────────
r = httpx.post(f"{BASE}/events/ingest", json=[{"garbage": "data"}, {"also": "bad"}])
body = r.json()
check(
    "Malformed events return 200 (not 5xx) with errors list",
    r.status_code == 200
    and body.get("rejected", 0) > 0
    and isinstance(body.get("errors"), list)
    and len(body["errors"]) > 0,
    f"got {body}",
)

# ── 5. GET /stores/{id}/metrics returns all required fields ───────────────────
r = httpx.get(f"{BASE}/stores/{STORE_ID}/metrics")
body = r.json()
required = {"store_id","date","unique_visitors","conversion_rate",
            "avg_dwell_by_zone","queue_depth","abandonment_rate","computed_at"}
check(
    "Metrics returns all required fields",
    r.status_code == 200 and required.issubset(body.keys()),
    f"missing: {required - set(body.keys())}",
)

# ── 6. conversion_rate is a float between 0 and 1 ─────────────────────────────
check(
    "conversion_rate is float in [0, 1]",
    isinstance(body.get("conversion_rate"), float)
    and 0.0 <= body.get("conversion_rate", -1) <= 1.0,
    f"got conversion_rate={body.get('conversion_rate')}",
)

# ── 7. GET /stores/{id}/funnel returns 4 stages in correct order ───────────────
r = httpx.get(f"{BASE}/stores/{STORE_ID}/funnel")
stages = r.json()
check(
    "Funnel returns 4 stages in correct order",
    r.status_code == 200
    and isinstance(stages, list)
    and len(stages) == 4
    and [s["stage"] for s in stages] == ["entry","zone_visit","billing_queue","purchase"],
    f"got {[s.get('stage') for s in stages] if isinstance(stages, list) else stages}",
)

# ── 8. Staff events excluded from unique_visitors ──────────────────────────────
# Use a dedicated isolated store so staff test events don't pollute STORE_BLR_002.
# The store name makes it clear this is a test-only store.
staff_store = "STORE_ASSERT_STAFF_ONLY"
staff_event = make_event(
    event_id=str(uuid.uuid4()), store_id=staff_store,
    visitor_id=f"VIS_{uuid.uuid4().hex[:6]}", is_staff=True,
)
httpx.post(f"{BASE}/events/ingest", json=[staff_event])
r = httpx.get(f"{BASE}/stores/{staff_store}/metrics")
body = r.json()
check(
    "Staff events excluded from unique_visitors",
    r.status_code == 200 and body.get("unique_visitors", -1) == 0,
    f"got unique_visitors={body.get('unique_visitors')}",
)

# ── 9. GET /stores/{id}/heatmap returns proper structure ──────────────────────
r = httpx.get(f"{BASE}/stores/{STORE_ID}/heatmap")
body = r.json()
check(
    "Heatmap returns store_id, zones list, data_confidence",
    r.status_code == 200
    and body.get("store_id") == STORE_ID
    and isinstance(body.get("zones"), list)
    and body.get("data_confidence") in ("ok", "low"),
    f"got {body}",
)

# ── 10. GET /stores/{id}/anomalies returns proper structure ───────────────────
r = httpx.get(f"{BASE}/stores/{STORE_ID}/anomalies")
body = r.json()
check(
    "Anomalies returns store_id and anomalies list (empty is valid)",
    r.status_code == 200
    and body.get("store_id") == STORE_ID
    and isinstance(body.get("anomalies"), list),
    f"got {body}",
)

# ── Summary ───────────────────────────────────────────────────────────────────
total = PASSED + FAILED
print(f"\n{'='*58}")
print(f"  Result: {PASSED}/{total} passed", end="")
if FAILED == 0:
    print("  🎉 All assertions passed!")
else:
    print(f"  ({FAILED} failed)")
print(f"{'='*58}\n")

sys.exit(0 if FAILED == 0 else 1)
