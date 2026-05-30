# Store Intelligence System — Architecture

**Project:** Purplle Tech Challenge 2026, Round 2  
**North Star Metric:** `Conversion Rate = Unique purchasing visitors ÷ Total unique visitors (per session window)`

---

## 0. Provided Dataset Files (Critical Inputs)

These four files are provided by Purplle as part of the challenge dataset ZIP. **The entire system depends on them.** Without them, the pipeline cannot run, the API cannot correlate purchases, and the output cannot be validated. They must be placed in `data/` before any code runs.

```
data/
├── store_layout.json       ← Pipeline reads this to know zones and cameras
├── pos_transactions.csv    ← API loads this to compute conversion rate
├── sample_events.jsonl     ← Pipeline validates output schema against this
└── assertions.py           ← API must pass all 10 assertions to score
```

---

### 0.1 `store_layout.json` — Zone & Camera Definitions

**What it contains:** One entry per store. For each store: the list of named zones with their polygon coordinates, which cameras cover which zones, and the store's open hours.

**Who reads it:**
- `pipeline/zone_classifier.py` — loads zone polygons to classify which zone a tracked person is in
- `pipeline/detect.py` — reads camera IDs to populate the `camera_id` field in events
- `pipeline/emit.py` — reads zone names to populate `zone_id` and `metadata.sku_zone` in events
- `app/metrics.py` — reads zone names to build the heatmap structure (all zones must appear, even with zero visits)
- `app/health.py` — reads store open hours to suppress STALE_FEED warnings when the store is closed

**Expected structure (based on problem statement):**

```json
{
  "STORE_BLR_002": {
    "name": "Apex Retail Bangalore 002",
    "city": "Bangalore",
    "open_hours": { "start": "10:00", "end": "22:00" },
    "cameras": [
      { "camera_id": "CAM_ENTRY_01", "type": "entry_exit", "covers_zones": ["ENTRY_THRESHOLD"] },
      { "camera_id": "CAM_FLOOR_01", "type": "main_floor", "covers_zones": ["SKINCARE", "HAIRCARE", "FRAGRANCE"] },
      { "camera_id": "CAM_BILL_01",  "type": "billing",    "covers_zones": ["BILLING"] }
    ],
    "zones": [
      {
        "zone_id": "SKINCARE",
        "sku_zone": "MOISTURISER",
        "polygon": [[120, 80], [340, 80], [340, 300], [120, 300]]
      },
      {
        "zone_id": "BILLING",
        "sku_zone": "BILLING",
        "polygon": [[400, 200], [600, 200], [600, 400], [400, 400]]
      }
    ]
  }
}
```

**What breaks without it:**
- Pipeline cannot classify zones → all `zone_id` fields would be null → zero ZONE_ENTER/EXIT/DWELL events
- `camera_id` in events would be unknown → schema validation failures
- `/heatmap` endpoint cannot return the full zone list → incomplete response
- Dead-zone anomaly detection cannot check all zones → false negatives

**How the pipeline uses it:**

```
store_layout.json
      │
      ├──► zone_classifier.py
      │         Loads polygon coordinates for each zone
      │         For every tracked person: checks if centroid is inside any polygon
      │         Emits ZONE_ENTER when centroid first enters polygon
      │         Emits ZONE_EXIT when centroid leaves polygon
      │         Emits ZONE_DWELL every 30s of continuous presence
      │
      ├──► detect.py
      │         Reads camera_id list to tag which camera produced each detection
      │
      └──► emit.py
                Reads zone_id and sku_zone to populate event metadata fields
```

---

### 0.2 `pos_transactions.csv` — Point-of-Sale Records

**What it contains:** Every purchase transaction across all stores. No customer identity — correlation is done purely by time window + store.

**Schema (from problem statement):**

```
store_id, transaction_id, timestamp, basket_value_inr
STORE_BLR_002, TXN_00441, 2026-03-03T14:38:12Z, 1240.00
STORE_BLR_002, TXN_00442, 2026-03-03T14:41:55Z, 680.00
```

| Column | Type | Description |
|--------|------|-------------|
| `store_id` | string | Matches store IDs in `store_layout.json` |
| `transaction_id` | string | Unique transaction identifier (e.g. `TXN_00441`) |
| `timestamp` | ISO-8601 UTC | When the transaction occurred at the POS terminal |
| `basket_value_inr` | float | Transaction value in Indian Rupees |

**Who reads it:**
- `app/db.py` (startup) — loads entire CSV into `pos_transactions` table on API startup
- `app/metrics.py` — queries it to compute `conversion_rate` and `abandonment_rate`
- `app/funnel.py` — queries it to determine which sessions reached the Purchase stage

**Correlation rule (critical):** A visitor who was in the billing zone in the **5-minute window before** a transaction timestamp counts as converted for that session. There is no `customer_id` — this time-window join is the only way to link a purchase to a visitor.

```
Visitor VIS_abc in billing zone: 14:33:00 → 14:38:30
Transaction TXN_00441 at STORE_BLR_002: 14:38:12

Window check: was visitor in billing zone between
  14:38:12 - 5min = 14:33:12  and  14:38:12?
  YES (visitor was there 14:33:00–14:38:30)
  → visitor marked converted = true
```

**What breaks without it:**
- `conversion_rate` is always 0.0 or undefined
- `BILLING_QUEUE_ABANDON` cannot be detected (requires checking if POS followed the billing zone exit)
- `/funnel` Purchase stage count is always 0
- Anomaly `CONVERSION_DROP` cannot be computed

**Loading strategy:**

```
API startup
    │
    └──► db.py: load_pos_data()
              Read pos_transactions.csv with csv.DictReader
              Bulk INSERT into pos_transactions table
              ON CONFLICT (transaction_id) DO NOTHING   ← safe to restart
              Log row count on success
```

---

### 0.3 `sample_events.jsonl` — Reference Event Output (200 events)

**What it contains:** 200 example events in the exact schema the pipeline must emit. These are pre-validated correct outputs used to verify that your pipeline's event format matches what the scoring harness expects.

**Format:** One JSON object per line (JSONL / newline-delimited JSON).

```jsonl
{"event_id": "550e8400-e29b-41d4-a716-446655440000", "store_id": "STORE_BLR_002", "camera_id": "CAM_ENTRY_01", "visitor_id": "VIS_c8a2f1", "event_type": "ENTRY", "timestamp": "2026-03-03T14:22:10Z", "zone_id": null, "dwell_ms": 0, "is_staff": false, "confidence": 0.91, "metadata": {"queue_depth": null, "sku_zone": null, "session_seq": 1}}
{"event_id": "661f9511-f30c-52e5-b827-557766551111", "store_id": "STORE_BLR_002", "camera_id": "CAM_FLOOR_01", "visitor_id": "VIS_c8a2f1", "event_type": "ZONE_ENTER", "timestamp": "2026-03-03T14:22:45Z", "zone_id": "SKINCARE", "dwell_ms": 0, "is_staff": false, "confidence": 0.88, "metadata": {"queue_depth": null, "sku_zone": "MOISTURISER", "session_seq": 2}}
```

**Who reads it:**
- `pipeline/emit.py` (development) — compare your output structure field-by-field against these examples
- `tests/test_pipeline.py` — load sample events as fixtures to assert schema compliance
- `tests/conftest.py` — use sample events to seed the test database for API tests

**How to use it:**

```python
# In tests/conftest.py
import json

def load_sample_events(path="data/sample_events.jsonl"):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]

# Validate your pipeline output matches the reference schema
def test_schema_compliance(pipeline_output_events, sample_events):
    sample_keys = set(sample_events[0].keys())
    for event in pipeline_output_events:
        assert set(event.keys()) == sample_keys, f"Missing fields: {sample_keys - set(event.keys())}"
        assert event["metadata"].keys() == {"queue_depth", "sku_zone", "session_seq"}
```

**Key things to verify from sample events:**
- Exact field names (snake_case, no camelCase)
- `visitor_id` format: `VIS_` prefix + 6-char hex
- `timestamp` format: ISO-8601 with `Z` suffix (not `+00:00`)
- `zone_id` is `null` (JSON null) for ENTRY/EXIT — not an empty string
- `dwell_ms` is integer `0` for instantaneous events — not `null`
- `metadata` object always present with all three keys — never missing

**What breaks without it:**
- No reference to validate pipeline output schema against
- Test fixtures have no authoritative source — tests may pass against wrong schema
- Risk of subtle format mismatches (e.g., `+00:00` vs `Z`) that cause scoring harness failures

---

### 0.4 `assertions.py` — API Scoring Assertions (10 tests)

**What it contains:** 10 pre-written assertions that the scoring harness runs against your live API. These are a subset of the full test suite — passing all 10 is necessary but not sufficient for full Part B marks.

**How it works:** The file sends HTTP requests to your running API and asserts on the responses. It is not a pytest file — it runs against your live Docker container.

**Expected structure (based on problem statement):**

```python
import requests

BASE = "http://localhost:8000"

# Assertion 1: Health endpoint returns 200
resp = requests.get(f"{BASE}/health")
assert resp.status_code == 200
assert "stores" in resp.json()

# Assertion 2: Metrics endpoint returns required fields
resp = requests.get(f"{BASE}/stores/STORE_BLR_002/metrics")
assert resp.status_code == 200
data = resp.json()
assert "unique_visitors" in data
assert "conversion_rate" in data
assert isinstance(data["conversion_rate"], float)

# Assertion 3: Ingest is idempotent
payload = [...]  # sample events
resp1 = requests.post(f"{BASE}/events/ingest", json=payload)
resp2 = requests.post(f"{BASE}/events/ingest", json=payload)
assert resp1.json()["accepted"] == resp2.json()["accepted"]

# Assertion 4: Malformed events return structured errors (not 5xx)
resp = requests.post(f"{BASE}/events/ingest", json=[{"bad": "data"}])
assert resp.status_code == 200          # partial success, not 5xx
assert resp.json()["rejected"] > 0
assert len(resp.json()["errors"]) > 0

# Assertion 5: Funnel returns 4 stages
resp = requests.get(f"{BASE}/stores/STORE_BLR_002/funnel")
assert resp.status_code == 200
stages = resp.json()
assert len(stages) == 4
stage_names = [s["stage"] for s in stages]
assert "entry" in stage_names
assert "purchase" in stage_names

# ... (assertions 6–10 cover heatmap, anomalies, staff exclusion, zero-store, STALE_FEED)
```

**Who uses it:**
- You run it manually during development: `python assertions.py`
- The scoring harness runs it automatically against your submitted Docker container
- `tests/` should include the same assertions as proper pytest tests with fixtures

**Critical: run this before submission.** Every assertion that fails costs points directly from Part B (API endpoint correctness — 20 pts) and Part B funnel accuracy (10 pts).

**What breaks without it:**
- No way to verify API output matches the scoring harness expectations
- Risk of passing your own tests but failing the harness on format details (e.g., field names, data types)

---

### 0.5 File Dependency Map

```
                    store_layout.json
                          │
           ┌──────────────┼──────────────────────┐
           ▼              ▼                      ▼
    zone_classifier   detect.py              metrics.py
    (zone polygons)   (camera_id)            (zone list
           │              │                   for heatmap)
           └──────────────┘
                    │
                  emit.py
              (zone_id, sku_zone
               in every event)
                    │
                    ▼
            <store>.jsonl  ◄── validated against ── sample_events.jsonl
                    │
          POST /events/ingest
                    │
              PostgreSQL
           ┌────────┴────────┐
           │                 │
    events table      pos_transactions  ◄── loaded from ── pos_transactions.csv
           │                 │
     metrics.py         funnel.py
     (conversion        (Purchase
      rate, dwell)       stage count)
           │
     assertions.py ──► validates all API responses match expected format
```

---

## 1. Architecture Diagram

### 1.1 End-to-End System Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              STORE INTELLIGENCE SYSTEM                                  │
│                          Apex Retail — 40 Stores, 8 Cities                              │
└─────────────────────────────────────────────────────────────────────────────────────────┘

 ╔═══════════════════════════════════════════════════════════════════════════════════════╗
 ║  INPUT LAYER                                                                         ║
 ║                                                                                      ║
 ║   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌─────────────────────┐  ║
 ║   │  Entry/Exit  │   │  Main Floor  │   │   Billing    │   │  store_layout.json  │  ║
 ║   │  Camera      │   │  Camera      │   │   Camera     │   │  pos_transactions   │  ║
 ║   │  (CAM_ENTRY) │   │  (CAM_FLOOR) │   │  (CAM_BILL)  │   │  .csv               │  ║
 ║   │  1080p 15fps │   │  1080p 15fps │   │  1080p 15fps │   │                     │  ║
 ║   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────────┬──────────┘  ║
 ║          │                  │                   │                      │             ║
 ╚══════════╪══════════════════╪═══════════════════╪══════════════════════╪═════════════╝
            │                  │                   │                      │
            └──────────────────┴───────────────────┘                      │
                               │                                          │
 ╔═════════════════════════════╪══════════════════════════════════════════╪═════════════╗
 ║  DETECTION LAYER  (pipeline/)│                                         │             ║
 ║                             ▼                                          │             ║
 ║   ┌─────────────────────────────────────────────────────────────┐      │             ║
 ║   │                     detect.py                               │      │             ║
 ║   │                                                             │      │             ║
 ║   │   Frame ──► YOLOv9 ──► Person BBoxes + Confidence          │      │             ║
 ║   │                │                                            │      │             ║
 ║   │                ▼                                            │      │             ║
 ║   │           ByteTrack ──► Persistent Track IDs               │      │             ║
 ║   │                │         (survives occlusion)               │      │             ║
 ║   │                ▼                                            │      │             ║
 ║   │        Upper-body ROI ──► Staff Classifier                  │      │             ║
 ║   │                │         (color histogram)                  │      │             ║
 ║   │                ▼                                            │      │             ║
 ║   │         Zone Classifier ──► Polygon intersection            │      │             ║
 ║   │         (store_layout.json)   with bbox centroid            │      │             ║
 ║   └────────────────────────────────────┬────────────────────────┘      │             ║
 ║                                        │                               │             ║
 ║   ┌────────────────────────────────────▼────────────────────────┐      │             ║
 ║   │                     tracker.py                              │      │             ║
 ║   │                                                             │      │             ║
 ║   │   Track ID ──► OSNet Re-ID ──► Appearance Embedding         │      │             ║
 ║   │                     │                                       │      │             ║
 ║   │                     ▼                                       │      │             ║
 ║   │           Embedding Store (in-memory, per store session)    │      │             ║
 ║   │                     │                                       │      │             ║
 ║   │         ┌───────────┴──────────────┐                        │      │             ║
 ║   │         ▼                          ▼                        │      │             ║
 ║   │   New visitor?              Matches prior EXIT?             │      │             ║
 ║   │   → assign VIS_<hash>       → reuse visitor_id             │      │             ║
 ║   │   → emit ENTRY              → emit REENTRY                  │      │             ║
 ║   │                                                             │      │             ║
 ║   │   Cross-camera overlap dedup:                               │      │             ║
 ║   │   Same embedding on floor cam within 30s of ENTRY?         │      │             ║
 ║   │   → suppress duplicate ZONE_ENTER                          │      │             ║
 ║   └────────────────────────────────────┬────────────────────────┘      │             ║
 ║                                        │                               │             ║
 ║   ┌────────────────────────────────────▼────────────────────────┐      │             ║
 ║   │                      emit.py                                │◄─────┘             ║
 ║   │                                                             │                   ║
 ║   │   Event assembler — builds schema-compliant JSON events     │                   ║
 ║   │   Writes to:  data/events/<store_id>.jsonl                  │                   ║
 ║   │   Also POST: → /events/ingest (batch, 500 at a time)        │                   ║
 ║   └────────────────────────────────────┬────────────────────────┘                   ║
 ╚════════════════════════════════════════╪═════════════════════════════════════════════╝
                                          │
                               POST /events/ingest
                               (batches of ≤500)
                                          │
 ╔════════════════════════════════════════╪═════════════════════════════════════════════╗
 ║  INTELLIGENCE API LAYER  (app/)        │                                             ║
 ║                                        ▼                                             ║
 ║   ┌────────────────────────────────────────────────────────────────────────────┐     ║
 ║   │                           FastAPI Application                              │     ║
 ║   │                                                                            │     ║
 ║   │   ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────────┐   │     ║
 ║   │   │  ingestion.py   │  │   metrics.py     │  │     funnel.py          │   │     ║
 ║   │   │                 │  │                  │  │                        │   │     ║
 ║   │   │ POST            │  │ GET              │  │ GET                    │   │     ║
 ║   │   │ /events/ingest  │  │ /stores/{id}     │  │ /stores/{id}           │   │     ║
 ║   │   │                 │  │ /metrics         │  │ /funnel                │   │     ║
 ║   │   │ • validate      │  │                  │  │                        │   │     ║
 ║   │   │ • dedup         │  │ • unique visitors│  │ • Entry→Zone→          │   │     ║
 ║   │   │   (ON CONFLICT  │  │ • conversion rate│  │   Billing→Purchase     │   │     ║
 ║   │   │    DO NOTHING)  │  │ • avg dwell/zone │  │ • drop-off % per stage │   │     ║
 ║   │   │ • partial accept│  │ • queue depth    │  │ • session dedup        │   │     ║
 ║   │   │ • structured err│  │ • abandon rate   │  │   (re-entry = 1 visit) │   │     ║
 ║   │   └────────┬────────┘  └────────┬─────────┘  └──────────┬─────────────┘   │     ║
 ║   │            │                    │                        │                 │     ║
 ║   │   ┌────────▼──────┐  ┌──────────▼──────────┐  ┌─────────▼──────────────┐  │     ║
 ║   │   │  anomalies.py │  │     health.py        │  │      heatmap           │  │     ║
 ║   │   │               │  │                      │  │   (in metrics.py)      │  │     ║
 ║   │   │ GET           │  │ GET /health          │  │                        │  │     ║
 ║   │   │ /stores/{id}  │  │                      │  │ GET /stores/{id}       │  │     ║
 ║   │   │ /anomalies    │  │ • service status     │  │ /heatmap               │  │     ║
 ║   │   │               │  │ • last event/store   │  │                        │  │     ║
 ║   │   │ • queue spike │  │ • STALE_FEED >10 min │  │ • zone freq + dwell    │  │     ║
 ║   │   │ • conv drop   │  │                      │  │ • normalized 0-100     │  │     ║
 ║   │   │ • dead zone   │  │                      │  │ • data_confidence flag │  │     ║
 ║   │   │ • INFO/WARN/  │  │                      │  │   if <20 sessions      │  │     ║
 ║   │   │   CRITICAL    │  │                      │  │                        │  │     ║
 ║   │   └───────────────┘  └──────────────────────┘  └────────────────────────┘  │     ║
 ║   │                                                                            │     ║
 ║   │   ┌──────────────────────────────────────────────────────────────────┐     │     ║
 ║   │   │                  Structured Logging Middleware                   │     │     ║
 ║   │   │   { trace_id, store_id, endpoint, latency_ms, event_count,       │     │     ║
 ║   │   │     status_code }  — every request, JSON format                  │     │     ║
 ║   │   └──────────────────────────────────────────────────────────────────┘     │     ║
 ║   └─────────────────────────────────────────┬──────────────────────────────────┘     ║
 ║                                             │                                        ║
 ║                              ┌──────────────┴──────────────┐                        ║
 ║                              │         PostgreSQL           │                        ║
 ║                              │                              │                        ║
 ║                              │  • events                    │                        ║
 ║                              │  • sessions                  │                        ║
 ║                              │  • pos_transactions          │                        ║
 ║                              │  • anomaly_baselines         │                        ║
 ║                              └──────────────────────────────┘                        ║
 ╚════════════════════════════════════════════════════════════════════════════════════════╝
                                             │
                                    WebSocket broadcast
                                             │
 ╔═══════════════════════════════════════════╪════════════════════════════════════════════╗
 ║  LIVE DASHBOARD LAYER  (app/dashboard/)   │                                           ║
 ║                                           ▼                                           ║
 ║   ┌────────────────────────────────────────────────────────────────────────────────┐  ║
 ║   │                      Browser — index.html (Vanilla JS)                        │  ║
 ║   │                                                                                │  ║
 ║   │   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐   │  ║
 ║   │   │  Visitor Count   │  │ Conversion Rate  │  │     Queue Depth          │   │  ║
 ║   │   │   [live count]   │  │   [live %]       │  │   [live integer]         │   │  ║
 ║   │   └──────────────────┘  └──────────────────┘  └──────────────────────────┘   │  ║
 ║   │                                                                                │  ║
 ║   │                          [Live Line Chart]                                    │  ║
 ║   │                    Visitor count over last 30 minutes                         │  ║
 ║   └────────────────────────────────────────────────────────────────────────────────┘  ║
 ╚════════════════════════════════════════════════════════════════════════════════════════╝
```

### 1.2 Data Flow — Event Lifecycle

```
 Frame N                Frame N+30            Frame N+450
    │                      │                      │
    ▼                      ▼                      ▼
 [YOLOv9]             [YOLOv9]              [YOLOv9]
 BBox(person)         BBox(person)          BBox(person)
    │                      │                      │
    ▼                      ▼                      ▼
 [ByteTrack]          [ByteTrack]           [ByteTrack]
 track_id=7           track_id=7            track_id=7
    │                      │                      │
    ▼                      ▼                      ▼
 [OSNet Re-ID]        [OSNet Re-ID]         [OSNet Re-ID]
 NEW visitor          SAME visitor          SAME visitor
 → VIS_abc123         → VIS_abc123          → VIS_abc123
    │                      │                      │
    ▼                      ▼                      ▼
 [emit.py]            [emit.py]             [emit.py]
 ENTRY event          ZONE_ENTER event      ZONE_DWELL event
 zone_id=null         zone_id=SKINCARE      dwell_ms=30000
    │                      │                      │
    └──────────────────────┴──────────────────────┘
                           │
                  POST /events/ingest
                  (batch of 3 events)
                           │
                    [ingestion.py]
                    validate schema
                    INSERT ON CONFLICT DO NOTHING
                    return { accepted:3, rejected:0 }
                           │
                    [PostgreSQL: events table]
                           │
              ┌────────────┴──────────────┐
              │                           │
      GET /metrics                 GET /funnel
      compute real-time            reconstruct session
      unique_visitors=1            Entry→Zone→Purchase
      conversion_rate=...          drop_off per stage
```

### 1.3 Re-ID and Re-Entry Decision Tree

```
 New track appears at entry threshold
              │
              ▼
    Extract OSNet embedding
              │
              ▼
   Search embedding store for
   recent EXITs (within 15 min,
   cosine similarity > 0.85)
              │
      ┌───────┴───────┐
      │               │
   MATCH           NO MATCH
      │               │
      ▼               ▼
  Reuse           New visitor_id
  visitor_id      VIS_<uuid_short>
      │               │
      ▼               ▼
  emit REENTRY    emit ENTRY
  (session_seq    (session_seq = 1)
   continues)
```

### 1.4 POS Correlation Flow

```
 Visitor VIS_abc123
 is in billing zone
 at 14:38:00
      │
      ▼
 BILLING_QUEUE_JOIN emitted
 queue_depth = 2
      │
      ├── Visitor exits billing zone at 14:41:00
      │              │
      │    POS lookup: any transaction at
      │    STORE_BLR_002 in window
      │    14:36:00–14:41:00?    ← (5-min pre-exit window)
      │              │
      │    ┌─────────┴──────────┐
      │    │                    │
      │  YES: TXN found      NO: No TXN
      │    │                    │
      │    ▼                    ▼
      │  visitor              emit BILLING_QUEUE_ABANDON
      │  marked converted     (never_purchased = true)
      │
      └── Reflected in /metrics conversion_rate
          and /funnel Purchase stage count
```

---

## 2. Folder Structure

```
store-intelligence/
│
├── pipeline/                        # Detection pipeline (runs against CCTV clips)
│   ├── detect.py                    # YOLOv9 inference + ByteTrack multi-object tracking
│   ├── tracker.py                   # OSNet Re-ID, visitor_id assignment, re-entry detection
│   ├── zone_classifier.py           # Polygon-based zone occupancy from store_layout.json
│   ├── staff_classifier.py          # Upper-body color histogram staff detection
│   ├── emit.py                      # Event schema assembly + JSONL writer + API poster
│   ├── replay.py                    # Replays JSONL at real-time speed for live dashboard
│   ├── run.sh                       # One command: process all clips → events JSONL
│   └── config.py                    # Configurable thresholds (confidence, Re-ID similarity)
│
├── app/                             # Intelligence API (FastAPI)
│   ├── main.py                      # FastAPI app factory, router mounts, middleware
│   ├── models.py                    # Pydantic request/response schemas + SQLAlchemy ORM models
│   ├── db.py                        # SQLAlchemy engine, session factory, connection pooling
│   ├── ingestion.py                 # POST /events/ingest — validate, dedup, persist
│   ├── metrics.py                   # GET /stores/{id}/metrics + GET /stores/{id}/heatmap
│   ├── funnel.py                    # GET /stores/{id}/funnel — session reconstruction
│   ├── anomalies.py                 # GET /stores/{id}/anomalies — spike/drop/dead-zone detection
│   ├── health.py                    # GET /health — staleness detection per store
│   ├── middleware.py                # Structured JSON logging middleware (trace_id injection)
│   ├── exceptions.py                # Global exception handlers (DB down → 503, no stack traces)
│   └── dashboard/
│       ├── index.html               # Live dashboard — WebSocket consumer, charts
│       └── ws.py                    # WebSocket endpoint + broadcaster
│
├── tests/                           # Test suite (target >70% statement coverage)
│   ├── conftest.py                  # pytest fixtures: in-memory DB, sample events, POS data
│   ├── test_pipeline.py             # Pipeline unit tests (event schema, staff exclusion, re-entry)
│   ├── test_ingestion.py            # Idempotency, partial success, malformed events
│   ├── test_metrics.py              # Metrics edge cases: empty store, all-staff, zero purchases
│   ├── test_funnel.py               # Funnel deduplication, re-entry handling
│   └── test_anomalies.py            # Queue spike, dead zone, conversion drop detection
│
├── docs/
│   ├── ARCHITECTURE.md              # This file
│   ├── DESIGN.md                    # Plain-language architecture + AI-Assisted Decisions
│   └── CHOICES.md                   # 3 decisions with full reasoning
│
├── data/                            # Gitignored — local only
│   ├── clips/                       # Raw CCTV clips (5 stores × 3 cameras × 20 min)
│   ├── store_layout.json            # Zone definitions (provided)
│   ├── pos_transactions.csv         # POS records (provided)
│   ├── sample_events.jsonl          # Reference events (provided)
│   └── events/                      # Pipeline output — one JSONL per store
│       ├── STORE_BLR_002.jsonl
│       └── ...
│
├── docker-compose.yml               # Services: api, postgres, pipeline-runner
├── Dockerfile                       # API service image (python:3.11-slim)
├── Dockerfile.pipeline              # Pipeline image (includes ultralytics, torchreid, CUDA)
├── requirements.txt                 # API dependencies
├── requirements-pipeline.txt        # Pipeline dependencies (heavier: torch, ultralytics)
├── .env.example                     # Environment variable template
├── .gitignore                       # Excludes data/, __pycache__, .env
└── README.md                        # Setup in ≤5 commands + pipeline instructions
```

---

## 3. Technology Stack

### 3.1 Detection Pipeline

| Component | Technology | Version | Rationale |
|-----------|------------|---------|-----------|
| Object detection | **YOLOv9** (ultralytics) | latest | Higher recall than v8 on partially-occluded persons; single-stage; ONNX-exportable for CPU fallback |
| Multi-object tracking | **ByteTrack** (via supervision) | latest | Maintains track IDs through full occlusion; low ID-switch rate; no appearance model required at track level |
| Person Re-ID | **OSNet** (torchreid) | 1.4 | Lightweight appearance embeddings; pretrained on Market-1501; runs on CPU in <5ms/crop |
| Zone classification | **Shapely** polygons | 2.x | Deterministic point-in-polygon from store_layout.json coordinates; no ML inference needed |
| Staff detection | **OpenCV** color histogram | 4.x | Upper-body HSV histogram vs reference uniform colors; fast, explainable |
| Video I/O | **OpenCV** / **decord** | 4.x | Frame extraction at configurable stride (every 3rd frame = 5fps effective) |
| Event emission | **Python stdlib** + **httpx** | 3.11 | Write JSONL locally; async POST batches to API |

### 3.2 Intelligence API

| Component | Technology | Version | Rationale |
|-----------|------------|---------|-----------|
| API framework | **FastAPI** | 0.110+ | Scoring harness has best FastAPI coverage; native async; Pydantic validation built-in |
| Data validation | **Pydantic v2** | 2.x | Schema-first; fast validation; clear error messages for partial success |
| ORM | **SQLAlchemy** | 2.x | Async-compatible; clean ORM models; connection pooling built-in |
| Database | **PostgreSQL** | 16 | ACID transactions for idempotency; concurrent writes; JSONB for metadata; production-aware |
| DB migrations | **Alembic** | 1.x | Version-controlled schema; reproducible from scratch |
| HTTP client (pipeline→API) | **httpx** | 0.27 | Async; connection pooling; retry logic |
| Testing | **pytest** + **pytest-cov** | latest | Coverage measurement; async test support via pytest-asyncio |
| Test DB | **pytest** + **SQLite in-memory** | — | Fast, isolated test runs without Docker requirement |

### 3.3 Infrastructure

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Containerisation | **Docker Compose** | Acceptance gate requirement; zero manual setup |
| API container | `python:3.11-slim` | Minimal attack surface; small image |
| Pipeline container | `pytorch/pytorch:2.2-cuda12.1` | CUDA support for YOLOv9 inference; falls back gracefully to CPU |
| Process manager | **Uvicorn** | FastAPI's native ASGI server; production-grade |
| Logging | **structlog** | JSON output with trace_id injection; matches scoring requirement exactly |
| Live dashboard transport | **FastAPI WebSockets** | No extra infra; same process as API |

### 3.4 Dependency Separation

```
requirements.txt (API — lightweight)
  fastapi, uvicorn, sqlalchemy, alembic, pydantic, psycopg2-binary,
  structlog, httpx, python-dotenv

requirements-pipeline.txt (Detection — heavy)
  ultralytics, torchreid, supervision, opencv-python-headless,
  shapely, numpy, decord, httpx
```

---

## 4. Database Schema

### 4.1 Entity Relationship Diagram

```
 ┌───────────────────────────────────────────────────────────────────────────┐
 │                            events                                         │
 │                                                                           │
 │  event_id       UUID        PRIMARY KEY                                   │
 │  store_id       VARCHAR(32) NOT NULL  ─────────────────────────────────┐  │
 │  camera_id      VARCHAR(32) NOT NULL                                    │  │
 │  visitor_id     VARCHAR(32) NOT NULL  ──────────────────────────────┐   │  │
 │  event_type     VARCHAR(32) NOT NULL                                │   │  │
 │  timestamp      TIMESTAMPTZ NOT NULL                                │   │  │
 │  zone_id        VARCHAR(64) NULLABLE                                │   │  │
 │  dwell_ms       INTEGER     NOT NULL  DEFAULT 0                     │   │  │
 │  is_staff       BOOLEAN     NOT NULL  DEFAULT false                 │   │  │
 │  confidence     FLOAT       NOT NULL                                │   │  │
 │  queue_depth    INTEGER     NULLABLE                                │   │  │
 │  sku_zone       VARCHAR(64) NULLABLE                                │   │  │
 │  session_seq    INTEGER     NOT NULL  DEFAULT 1                     │   │  │
 │  ingested_at    TIMESTAMPTZ NOT NULL  DEFAULT NOW()                 │   │  │
 │                                                                     │   │  │
 │  INDEX  (store_id, timestamp)          ← metrics queries            │   │  │
 │  INDEX  (visitor_id, store_id)         ← session reconstruction     │   │  │
 │  INDEX  (store_id, event_type, timestamp) ← anomaly queries         │   │  │
 │  INDEX  (store_id, is_staff, timestamp)   ← staff exclusion         │   │  │
 └─────────────────────────────────────────────┬───────────────────────┘   │  │
                                               │                           │  │
                                               │                           │  │
 ┌─────────────────────────────────────────────▼───────────────────────────┘  │
 │                            sessions                                        │
 │  (materialised view / table refreshed on each ingest)                      │
 │                                                                            │
 │  session_id     UUID        PRIMARY KEY                                    │
 │  store_id       VARCHAR(32) NOT NULL                                       │
 │  visitor_id     VARCHAR(32) NOT NULL ◄──────────────────────────────────┘  │
 │  entry_time     TIMESTAMPTZ NOT NULL                                       │
 │  exit_time      TIMESTAMPTZ NULLABLE                                       │
 │  is_staff       BOOLEAN     NOT NULL                                       │
 │  visited_zones  TEXT[]      NOT NULL  DEFAULT '{}'                         │
 │  reached_billing BOOLEAN    NOT NULL  DEFAULT false                        │
 │  converted      BOOLEAN     NOT NULL  DEFAULT false  ──────────────────┐   │
 │  session_date   DATE        NOT NULL  (partition key candidate)        │   │
 │                                                                        │   │
 │  UNIQUE (visitor_id, store_id, entry_time)  ← dedup re-entries        │   │
 │  INDEX  (store_id, session_date)            ← daily metrics           │   │
 └──────────────────────────────────────────────────┬─────────────────────┘   │
                                                    │                         │
 ┌──────────────────────────────────────────────────▼─────────────────────────┘
 │                          pos_transactions                                   │
 │  (loaded from pos_transactions.csv at startup)                             │
 │                                                                            │
 │  transaction_id  VARCHAR(32)  PRIMARY KEY                                  │
 │  store_id        VARCHAR(32)  NOT NULL                                     │
 │  timestamp       TIMESTAMPTZ  NOT NULL                                     │
 │  basket_value_inr NUMERIC(10,2) NOT NULL                                   │
 │                                                                            │
 │  INDEX (store_id, timestamp)  ← 5-minute correlation window lookup        │
 └────────────────────────────────────────────────────────────────────────────┘

 ┌────────────────────────────────────────────────────────────────────────────┐
 │                        anomaly_baselines                                   │
 │  (rolling 7-day statistics, updated daily)                                 │
 │                                                                            │
 │  id              SERIAL       PRIMARY KEY                                  │
 │  store_id        VARCHAR(32)  NOT NULL                                     │
 │  metric_name     VARCHAR(64)  NOT NULL  (e.g. conversion_rate, queue_depth)│
 │  hour_of_day     SMALLINT     NOT NULL  (0–23)                             │
 │  avg_7d          FLOAT        NOT NULL                                     │
 │  stddev_7d       FLOAT        NOT NULL                                     │
 │  computed_at     TIMESTAMPTZ  NOT NULL                                     │
 │                                                                            │
 │  UNIQUE (store_id, metric_name, hour_of_day)                               │
 └────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Key SQL Patterns

```sql
-- Idempotent event ingest
INSERT INTO events (...) VALUES (...)
ON CONFLICT (event_id) DO NOTHING;

-- Unique visitor count (staff excluded)
SELECT COUNT(DISTINCT visitor_id)
FROM sessions
WHERE store_id = $1
  AND session_date = CURRENT_DATE
  AND is_staff = false;

-- Conversion rate (POS correlation: 5-min pre-exit window)
SELECT
  COUNT(DISTINCT s.visitor_id) FILTER (WHERE s.converted) AS purchasers,
  COUNT(DISTINCT s.visitor_id) AS total_visitors,
  ROUND(
    COUNT(DISTINCT s.visitor_id) FILTER (WHERE s.converted)::NUMERIC
    / NULLIF(COUNT(DISTINCT s.visitor_id), 0) * 100,
    2
  ) AS conversion_rate_pct
FROM sessions s
WHERE s.store_id = $1
  AND s.session_date = CURRENT_DATE
  AND s.is_staff = false;

-- Session conversion flag (run at query time)
UPDATE sessions s
SET converted = true
WHERE EXISTS (
  SELECT 1 FROM pos_transactions p
  WHERE p.store_id = s.store_id
    AND p.timestamp BETWEEN (
      SELECT MAX(timestamp) FROM events
      WHERE visitor_id = s.visitor_id
        AND zone_id ILIKE '%BILLING%'
    ) - INTERVAL '5 minutes'
    AND (
      SELECT MAX(timestamp) FROM events
      WHERE visitor_id = s.visitor_id
        AND event_type = 'EXIT'
    )
);

-- Dead zone anomaly (no ZONE_ENTER in 30 min)
SELECT zone_id
FROM (
  SELECT DISTINCT zone_id FROM events
  WHERE store_id = $1 AND event_type = 'ZONE_ENTER'
) all_zones
WHERE zone_id NOT IN (
  SELECT DISTINCT zone_id FROM events
  WHERE store_id = $1
    AND event_type = 'ZONE_ENTER'
    AND timestamp > NOW() - INTERVAL '30 minutes'
);
```

---

## 5. Event Schema

### 5.1 Canonical Event Structure

Every event emitted by the detection pipeline and stored by the API must match this schema exactly.

```json
{
  "event_id":    "550e8400-e29b-41d4-a716-446655440000",
  "store_id":    "STORE_BLR_002",
  "camera_id":   "CAM_ENTRY_01",
  "visitor_id":  "VIS_c8a2f1",
  "event_type":  "ZONE_DWELL",
  "timestamp":   "2026-03-03T14:22:10Z",
  "zone_id":     "SKINCARE",
  "dwell_ms":    30000,
  "is_staff":    false,
  "confidence":  0.91,
  "metadata": {
    "queue_depth":  null,
    "sku_zone":     "MOISTURISER",
    "session_seq":  5
  }
}
```

### 5.2 Field Contracts

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| `event_id` | string (UUID v4) | Yes | Globally unique; generated by pipeline; idempotency key |
| `store_id` | string | Yes | Must match a key in `store_layout.json` |
| `camera_id` | string | Yes | Must match camera definition in `store_layout.json` |
| `visitor_id` | string | Yes | Format: `VIS_<6-char-hash>`; stable across cameras; new per session |
| `event_type` | string enum | Yes | One of the 8 types below; no other values accepted |
| `timestamp` | string (ISO-8601 UTC) | Yes | `clip_start_time + (frame_number / fps)` in UTC; ends with `Z` |
| `zone_id` | string \| null | Yes | Null for ENTRY and EXIT; zone name from `store_layout.json` for all others |
| `dwell_ms` | integer | Yes | Duration in milliseconds; `0` for instantaneous events (ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, BILLING_QUEUE_JOIN, BILLING_QUEUE_ABANDON, REENTRY) |
| `is_staff` | boolean | Yes | `true` if uniform detected; never null |
| `confidence` | float [0.0–1.0] | Yes | Detection confidence from model; never suppressed even if low |
| `metadata.queue_depth` | integer \| null | Yes | Integer ≥ 1 for BILLING_QUEUE_JOIN; null for all other types |
| `metadata.sku_zone` | string \| null | Yes | Zone label from `store_layout.json`; null when zone_id is null |
| `metadata.session_seq` | integer | Yes | 1-indexed ordinal position of this event within the visitor's session |

### 5.3 Event Type Catalogue

| Event Type | Trigger | `zone_id` | `dwell_ms` | `queue_depth` | Notes |
|-----------|---------|-----------|-----------|---------------|-------|
| `ENTRY` | Centroid crosses entry line inbound | `null` | `0` | `null` | Starts session; new `visitor_id` assigned; `session_seq = 1` |
| `EXIT` | Centroid crosses entry line outbound | `null` | `0` | `null` | Closes session; triggers POS correlation window |
| `ZONE_ENTER` | Centroid enters zone polygon | zone name | `0` | `null` | Emitted once per zone entry |
| `ZONE_EXIT` | Centroid exits zone polygon | zone name | cumulative dwell | `null` | `dwell_ms` = total time spent in zone this visit |
| `ZONE_DWELL` | 30+ seconds continuous in zone | zone name | 30000 per tick | `null` | Emitted every 30s of continued presence |
| `BILLING_QUEUE_JOIN` | Enters billing zone; ≥2 people in zone | billing zone | `0` | integer ≥ 1 | `queue_depth` = persons in zone at join moment |
| `BILLING_QUEUE_ABANDON` | Exits billing zone; no POS in next 5 min | billing zone | cumulative dwell | `null` | Requires POS correlation; may be determined at API layer |
| `REENTRY` | Visitor seen after prior EXIT; Re-ID match | `null` | `0` | `null` | Reuses original `visitor_id`; does NOT reset `session_seq` |

### 5.4 Pydantic Schema (Python)

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from enum import Enum

class EventType(str, Enum):
    ENTRY                = "ENTRY"
    EXIT                 = "EXIT"
    ZONE_ENTER           = "ZONE_ENTER"
    ZONE_EXIT            = "ZONE_EXIT"
    ZONE_DWELL           = "ZONE_DWELL"
    BILLING_QUEUE_JOIN   = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY              = "REENTRY"

class EventMetadata(BaseModel):
    queue_depth:  Optional[int]   = None
    sku_zone:     Optional[str]   = None
    session_seq:  int             = Field(ge=1)

class StoreEvent(BaseModel):
    event_id:   UUID
    store_id:   str
    camera_id:  str
    visitor_id: str               = Field(pattern=r'^VIS_[a-f0-9]{6}$')
    event_type: EventType
    timestamp:  datetime
    zone_id:    Optional[str]     = None
    dwell_ms:   int               = Field(ge=0, default=0)
    is_staff:   bool
    confidence: float             = Field(ge=0.0, le=1.0)
    metadata:   EventMetadata

    class Config:
        json_encoders = {datetime: lambda v: v.strftime('%Y-%m-%dT%H:%M:%SZ')}
```

### 5.5 Ingest API Response Schema

```json
{
  "accepted":  47,
  "rejected":   3,
  "errors": [
    {
      "event_id": "bad-uuid",
      "reason":   "event_id must be a valid UUID v4"
    },
    {
      "event_id": "550e8400-...",
      "reason":   "confidence must be between 0.0 and 1.0, got 1.5"
    }
  ]
}
```

---

## 6. Development Roadmap

### Phase Overview

```
 Hour  0     6    12    18    24    30    36    42    48
       │     │     │     │     │     │     │     │     │
       ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼
  ─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────
       │  M0 │  M1 │  M2 │  M3 │  M4 │  M5 │  M6 │ M7 │
  ─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────
   0-1  1-8  8-14 14-18 18-26 26-32 32-38 38-44 44-48
  Setup Detect Edge  Ingest Analyt Prod  AI    Dash Final
              Cases  API    Endpts Ready Docs  board  QA
```

### M0 — Environment & Dataset (Hours 0–1)

**Goal:** Everything bootstrapped; data understood; repo initialised.

| Task | Detail |
|------|--------|
| Initialise git repo | Suggested structure from problem statement |
| Inspect dataset | Parse store_layout.json zone polygon format; review sample_events.jsonl schema |
| Run assertions.py | Understand the test format and what the scoring harness expects |
| Bootstrap Docker | docker-compose.yml with postgres service; verify `docker compose up` works |
| Install dependencies | Two requirements files; verify YOLOv9 loads |
| Stub DESIGN.md + CHOICES.md | Empty files with headings to fill in throughout |

**Exit criteria:** `docker compose up` brings up Postgres; `python -c "from ultralytics import YOLO"` succeeds.

---

### M1 — Detection Pipeline Core (Hours 1–8)

**Goal:** Pipeline processes one clip, emits schema-compliant events.

| Task | Detail | Scoring |
|------|--------|---------|
| `detect.py` | YOLOv9 inference on frames; filter class=person; extract confidence | 10 pts entry/exit accuracy |
| `tracker.py` (tracking) | ByteTrack integration; assign persistent track_id; maintain across frames | 10 pts |
| `zone_classifier.py` | Load zone polygons; point-in-polygon per track centroid; emit ZONE_ENTER/EXIT | 10 pts schema |
| `staff_classifier.py` | HSV histogram on upper-body ROI; threshold-based is_staff flag | 10 pts staff excl. |
| `emit.py` (core) | UUID generation; timestamp from clip_start + frame/fps; JSONL write | 10 pts schema |
| ENTRY/EXIT detection | Threshold line crossing; direction via centroid delta-y; emit ENTRY or EXIT | 10 pts accuracy |
| Group entry | NMS threshold tuning; count overlapping detections as individuals | 10 pts group handling |

**Exit criteria:** `pipeline/run.sh data/clips/STORE_BLR_002/` produces a valid JSONL file with ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL events that validate against sample_events.jsonl schema.

---

### M2 — Detection Edge Cases (Hours 8–14)

**Goal:** Re-ID, re-entry, cross-camera dedup, queue tracking, all 8 event types.

| Task | Detail | Scoring |
|------|--------|---------|
| OSNet Re-ID | Extract embeddings per track; cosine similarity comparison | 10 pts re-entry |
| Re-entry detection | Match new track vs recent EXIT embeddings (15-min window, >0.85 similarity) | 10 pts |
| Cross-camera dedup | Suppress duplicate ZONE_ENTER when floor + entry cameras overlap | 10 pts accuracy |
| `REENTRY` event | Emit REENTRY (not ENTRY) on match; reuse visitor_id | 10 pts |
| `BILLING_QUEUE_JOIN` | Count persons in billing zone polygon; emit when new joiner + count >1 | 5 pts anomaly |
| `BILLING_QUEUE_ABANDON` | Detect exit without subsequent POS match; emit BILLING_QUEUE_ABANDON | 10 pts funnel |
| Empty store handling | Pipeline produces empty/zero-event JSONL without crashing | 5 pts prod |
| Partial occlusion | ByteTrack maintains track through occlusion; confidence decreases gracefully | 10 pts confidence |
| Process all 15 clips | Run pipeline on all stores | — |

**Exit criteria:** All 8 event types appear in JSONL output; re-entry on same person produces REENTRY not ENTRY; group of 3 produces 3 ENTRY events.

---

### M3 — Intelligence API: Ingestion (Hours 14–18)

**Goal:** `POST /events/ingest` working, idempotent, production-grade.

| Task | Detail | Scoring |
|------|--------|---------|
| `models.py` | Pydantic EventSchema + SQLAlchemy ORM for events, sessions, pos_transactions | 20 pts API |
| DB migrations | Alembic init_db; create all tables with indexes | Gate |
| `ingestion.py` | Validate batch; `INSERT ... ON CONFLICT DO NOTHING`; collect errors per event | 20 pts |
| POS data loader | Load pos_transactions.csv into DB at startup | 10 pts funnel |
| `main.py` | FastAPI app; mount ingestion router | Gate |
| Structured logging | `middleware.py`; inject trace_id; log all fields; JSON format | 5 pts logs |
| Graceful DB failure | Wrap all DB calls; return 503 with structured body | 5 pts prod |

**Exit criteria:** POST same 100 events twice → DB has 100 rows; POST 50 valid + 5 malformed → `{accepted:50, rejected:5, errors:[...]}` with 200 status (not 5xx).

---

### M4 — Intelligence API: Analytics (Hours 18–26)

**Goal:** All 5 analytics endpoints correct.

| Task | Endpoint | Key Complexity | Scoring |
|------|----------|---------------|---------|
| `metrics.py` | `GET /stores/{id}/metrics` | Staff exclusion; zero-purchase handling; POS correlation | 20 pts API |
| `funnel.py` | `GET /stores/{id}/funnel` | Session reconstruction; re-entry dedup (visitor appears once) | 10 pts funnel |
| Heatmap | `GET /stores/{id}/heatmap` | Normalize 0–100; data_confidence flag <20 sessions | 20 pts API |
| `anomalies.py` | `GET /stores/{id}/anomalies` | Queue spike vs 7-day avg; dead zone 30 min; conversion drop 20% | 5 pts anomaly |
| `health.py` | `GET /health` | Per-store last event; STALE_FEED flag >10 min lag | 5 pts logs |

**Exit criteria:** `assertions.py` passes; zero-purchase store returns `conversion_rate: 0.0`; all-staff clip returns `unique_visitors: 0`.

---

### M5 — Production Readiness (Hours 26–32)

**Goal:** Passes acceptance gate; Part C fully addressed.

| Task | Detail | Scoring |
|------|--------|---------|
| `docker-compose.yml` | api + postgres + health checks + env vars; no manual steps | 5 pts gate |
| `Dockerfile` | Multi-stage; non-root user; COPY requirements first for cache | 5 pts |
| README.md | ≤5 commands: clone, env, compose up, run pipeline, hit API | 5 pts gate |
| Test: idempotency | `test_ingestion.py` — POST same payload twice; assert row count unchanged | 10 pts tests |
| Test: empty store | `test_metrics.py` — zero events → valid JSON response | 10 pts tests |
| Test: all-staff | `test_metrics.py` — only is_staff=true events → unique_visitors=0 | 10 pts tests |
| Test: re-entry funnel | `test_funnel.py` — REENTRY visitor counted once in funnel | 10 pts tests |
| Coverage gate | `pytest --cov=app --cov-report=term` — achieve >70% | 10 pts tests |
| No stack traces | `exceptions.py` — all DB errors return structured 503 | 5 pts prod |

**Exit criteria:** `docker compose up` from git clone; all acceptance gate criteria pass; coverage >70%.

---

### M6 — AI Documentation (Hours 32–38)

**Goal:** Part D (15 pts) fully captured.

| Deliverable | Content | Scoring |
|------------|---------|---------|
| Prompt blocks | Top of each test file: `# PROMPT: <exact prompt> / # CHANGES MADE: <what changed>` | 15 pts AI |
| `DESIGN.md` | Architecture diagram (ASCII); data flow; component roles; **"AI-Assisted Decisions"** section with ≥2 examples where AI shaped design (with your override/acceptance and why) | 15 pts |
| `CHOICES.md` | **Decision 1:** Detection model — YOLOv8 vs YOLOv9 vs RT-DETR vs MediaPipe; AI recommendation; what you chose and why. **Decision 2:** Event schema — why confidence passthrough, why session_seq, metadata structure rationale. **Decision 3:** API architecture — SQLite vs PostgreSQL; session reconstruction at query time vs at ingest; caching strategy | 15 pts |
| VLM usage doc | If Claude Vision / GPT-4V used for zone classification or staff detection, document the exact prompt and whether it worked | 15 pts |

**Exit criteria:** Both docs >250 words; "AI-Assisted Decisions" section names specific LLM suggestions and your evaluation; CHOICES.md shows genuine reasoning, not filler.

---

### M7 — Live Dashboard (Hours 38–44)

**Goal:** +10 bonus points (web UI preferred over terminal).

| Task | Detail |
|------|--------|
| `app/dashboard/ws.py` | FastAPI WebSocket endpoint; broadcast `{store_id, unique_visitors, conversion_rate, queue_depth}` every 2s as events arrive |
| `pipeline/replay.py` | Read JSONL; respect original event timestamps; POST batches at replay speed (10× real-time); simulates live camera feed |
| `app/dashboard/index.html` | WebSocket consumer; live-updating number tiles; Chart.js line chart of visitor count over time |
| README update | Add dashboard URL and replay command |

**Exit criteria:** Start replay; open `http://localhost:8000/dashboard`; visitor count updates without page refresh.

---

### M8 — Final QA & Submission (Hours 44–48)

**Goal:** Ship with confidence; zero gate failures.

| Checklist Item |
|----------------|
| `git clone` → `docker compose up` → API running (no manual steps) |
| `pipeline/run.sh` → JSONL produced for all 5 stores |
| `POST /events/ingest` → 200, no 5xx |
| `GET /stores/STORE_BLR_002/metrics` → valid JSON, non-null fields |
| `GET /stores/STORE_BLR_002/funnel` → 4 stages with counts and drop-off % |
| `GET /stores/STORE_BLR_002/anomalies` → valid JSON (empty array is fine) |
| `GET /health` → per-store status, STALE_FEED logic works |
| `pytest --cov` → >70% statement coverage |
| `assertions.py` → all 10 pass |
| All 8 event types present in at least one JSONL file |
| `DESIGN.md` and `CHOICES.md` both >250 words |
| No stack traces appear in any API error response |
| Dashboard loads and updates (if implemented) |
| Push to private repo; share link with reviewer handle |

---

## Appendix: Anomaly Detection Logic

```
QUEUE_SPIKE
  condition:  current queue_depth > (7d_avg_queue_at_this_hour × 2)
  severity:   WARN if 2×; CRITICAL if 3×
  action:     "Open additional billing counter"

CONVERSION_DROP
  condition:  today_conversion_rate < (7d_avg_conversion_rate × 0.8)
  severity:   WARN if <80% of avg; CRITICAL if <60%
  action:     "Review floor staff positioning and zone engagement"

DEAD_ZONE
  condition:  no ZONE_ENTER events for any zone in past 30 minutes
              (during store open hours)
  severity:   INFO if one zone; WARN if >2 zones
  action:     "Check camera feed for <zone_id>; verify display setup"

STALE_FEED
  condition:  last ingested event for a store > 10 minutes ago
  severity:   CRITICAL
  location:   GET /health (not /anomalies)
  action:     "Check camera connectivity for STORE_<id>"
```
