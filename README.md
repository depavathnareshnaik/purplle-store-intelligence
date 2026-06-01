# Store Intelligence System

> **Apex Retail** — Raw CCTV footage → Live store analytics API  
> Purplle Tech Challenge 2026, Round 2

**North Star Metric:** `Conversion Rate = Unique purchasing visitors ÷ Total unique visitors`

---

## Quick Start

Five commands from a clean machine to a running API with real data:

```bash
# 1. Clone
git clone <repo-url> store-intelligence && cd store-intelligence

# 2. Configure environment
cp .env.example .env

# 3. Start the API + database (migrations run automatically on boot)
docker compose up --build -d

# 4. Ingest pre-generated events (1,148 real detections already in the repo)
pip install httpx && python3 scripts/ingest_events.py

# 5. Verify the API and open the live dashboard
curl -s http://localhost:8000/stores/STORE_BLR_002/metrics | python3 -m json.tool
```

> **Live dashboard:** `http://localhost:8000/dashboard`  
> **Swagger docs:** `http://localhost:8000/docs`
>
> **Note:** Step 4 ingests `data/events/STORE_BLR_002.jsonl` — the real detection
> output from running the pipeline on the Purplle Brigade Road footage.
> To re-run the detection pipeline yourself, see **Running the Detection Pipeline** below.
>
> **Acceptance gate:** `docker compose up` is the only manual step beyond `git clone`.  
> Alembic migrations run automatically at boot.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker + Docker Compose | 24+ | Runs API + PostgreSQL |
| Python | 3.11+ | Running the detection pipeline locally |
| CUDA (optional) | 12.1 | GPU acceleration for YOLOv8/YOLOv9 (falls back to CPU automatically) |

---

## Dataset Files

Place these four files (provided by Purplle) in the `data/` directory before running the pipeline:

```
data/
├── store_layout.json       ← Zone polygons + camera IDs (required by pipeline)
├── pos_transactions.csv    ← POS records (loaded into DB at API startup)
├── sample_events.jsonl     ← Reference events for pipeline validation
└── clips/
    ├── STORE_BLR_002/
    │   ├── entry_exit.mp4
    │   ├── main_floor.mp4
    │   └── billing.mp4
    └── ...                 ← One folder per store, 3 clips each
```

> **`pos_transactions.csv`** is loaded automatically when the API starts.  
> If the file is not present, the API still starts — conversion rate will be `0.0` until loaded.

---

## Running the Detection Pipeline

The pipeline processes CCTV clips and emits structured events to the API.

### Step-by-step

```bash
# Install pipeline dependencies (separate from the API — heavier, includes PyTorch)
pip install -r requirements-pipeline.txt

# Place dataset files in data/ as shown above

# Process all clips for all stores → outputs JSONL files
./pipeline/run.sh
# Output: data/events/STORE_BLR_002.jsonl, data/events/STORE_DEL_001.jsonl, ...

# Review output against the reference schema
head -5 data/events/STORE_BLR_002.jsonl | python3 -m json.tool

# Validate output matches sample_events.jsonl schema
python pipeline/validate.py

# Ingest all events into the running API
python pipeline/emit.py --api http://localhost:8000
# ↑ Posts JSONL files as batches of 500 to POST /events/ingest
```

### Pipeline configuration

Edit `pipeline/config.py` to tune detection thresholds:

| Setting | Default | Effect |
|---------|---------|--------|
| `CONFIDENCE_THRESHOLD` | `0.3` | Minimum YOLO detection confidence (events still emitted below this — only used for track filtering) |
| `REID_SIMILARITY_THRESHOLD` | `0.85` | Cosine similarity cutoff for re-entry matching |
| `REID_WINDOW_MINUTES` | `15` | How far back to search for re-entry embeddings |
| `FRAME_STRIDE` | `3` | Process every Nth frame (3 = 5fps effective at 15fps source) |

### What the pipeline produces

Each clip produces one JSONL file with one event per line:

```jsonl
{"event_id": "550e8400-...", "store_id": "STORE_BLR_002", "camera_id": "CAM_ENTRY_01", "visitor_id": "VIS_c8a2f1", "event_type": "ENTRY", "timestamp": "2026-03-03T14:22:10Z", "zone_id": null, "dwell_ms": 0, "is_staff": false, "confidence": 0.91, "metadata": {"queue_depth": null, "sku_zone": null, "session_seq": 1}}
{"event_id": "661f9511-...", "store_id": "STORE_BLR_002", "camera_id": "CAM_FLOOR_01", "visitor_id": "VIS_c8a2f1", "event_type": "ZONE_ENTER", "timestamp": "2026-03-03T14:22:45Z", "zone_id": "SKINCARE", "dwell_ms": 0, "is_staff": false, "confidence": 0.88, "metadata": {"queue_depth": null, "sku_zone": "MOISTURISER", "session_seq": 2}}
```

---

## API Reference

Base URL: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`

### `GET /health`

Service liveness + per-store feed freshness.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "service": "Store Intelligence API",
  "version": "1.0.0",
  "database": "connected",
  "stores": [
    {
      "store_id": "STORE_BLR_002",
      "last_event_at": "2026-03-03T14:30:00+00:00",
      "lag_minutes": 2.3,
      "status": "OK"
    }
  ],
  "checked_at": "2026-03-03T14:32:18+00:00"
}
```

`status: "STALE_FEED"` is raised for a store when no events have been received for **>10 minutes**.

---

### `POST /events/ingest`

Ingest a batch of detection events. Idempotent by `event_id`.

```bash
curl -X POST http://localhost:8000/events/ingest \
  -H "Content-Type: application/json" \
  -d '[
    {
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "store_id": "STORE_BLR_002",
      "camera_id": "CAM_ENTRY_01",
      "visitor_id": "VIS_c8a2f1",
      "event_type": "ENTRY",
      "timestamp": "2026-03-03T14:22:10Z",
      "zone_id": null,
      "dwell_ms": 0,
      "is_staff": false,
      "confidence": 0.91,
      "metadata": {"queue_depth": null, "sku_zone": null, "session_seq": 1}
    }
  ]'
```

```json
{ "accepted": 1, "rejected": 0, "errors": [] }
```

**Behaviour:**
- Max 500 events per request (HTTP 400 if exceeded)
- Posting the same `event_id` twice is safe — second write is silently ignored
- Malformed events return `rejected > 0` with per-event `errors` — **never** a 5xx

---

### `GET /stores/{store_id}/metrics`

Today's real-time store metrics.

```bash
curl http://localhost:8000/stores/STORE_BLR_002/metrics
```

```json
{
  "store_id": "STORE_BLR_002",
  "date": "2026-03-03",
  "unique_visitors": 47,
  "conversion_rate": 0.2128,
  "avg_dwell_by_zone": {
    "SKINCARE": 42000.0,
    "HAIRCARE": 28500.0,
    "FRAGRANCE": 15200.0
  },
  "queue_depth": 3,
  "abandonment_rate": 0.1250,
  "computed_at": "2026-03-03T14:30:00+00:00"
}
```

- `is_staff=true` visitors are excluded from all counts
- Zero-purchase stores return `conversion_rate: 0.0` — never null or error
- Real-time — not cached from yesterday

---

### `GET /stores/{store_id}/funnel`

Conversion funnel with drop-off percentages.

```bash
curl http://localhost:8000/stores/STORE_BLR_002/funnel
```

```json
[
  {"stage": "entry",         "count": 47,  "drop_off_pct": 0.0},
  {"stage": "zone_visit",    "count": 38,  "drop_off_pct": 19.15},
  {"stage": "billing_queue", "count": 21,  "drop_off_pct": 44.74},
  {"stage": "purchase",      "count": 10,  "drop_off_pct": 52.38}
]
```

The unit is the **session** (visitor), not raw events. A visitor who re-enters counts **once** at every stage.

---

### `GET /stores/{store_id}/heatmap`

Zone visit frequency and dwell time, normalized for grid rendering.

```bash
curl http://localhost:8000/stores/STORE_BLR_002/heatmap
```

```json
{
  "store_id": "STORE_BLR_002",
  "data_confidence": "ok",
  "zones": [
    {"zone_id": "SKINCARE",   "visit_count": 35, "avg_dwell_ms": 42000.0, "normalized_score": 100.0},
    {"zone_id": "HAIRCARE",   "visit_count": 24, "avg_dwell_ms": 28500.0, "normalized_score": 68.6},
    {"zone_id": "FRAGRANCE",  "visit_count": 12, "avg_dwell_ms": 15200.0, "normalized_score": 34.3}
  ],
  "computed_at": "2026-03-03T14:30:00+00:00"
}
```

`data_confidence: "low"` is set when fewer than 20 sessions exist — heatmap values are statistically unreliable at small sample sizes.

---

### `GET /stores/{store_id}/anomalies`

Active operational anomalies.

```bash
curl http://localhost:8000/stores/STORE_BLR_002/anomalies
```

```json
{
  "store_id": "STORE_BLR_002",
  "anomalies": [
    {
      "type": "QUEUE_SPIKE",
      "severity": "WARN",
      "suggested_action": "Open an additional billing counter immediately.",
      "detected_at": "2026-03-03T14:30:00+00:00",
      "details": {"current_depth": 8, "baseline_avg_7d": 3.2, "ratio": 2.5}
    }
  ],
  "computed_at": "2026-03-03T14:30:00+00:00"
}
```

| Type | Trigger | Severity |
|------|---------|---------|
| `QUEUE_SPIKE` | Current depth > 2× 7-day same-hour average | WARN / CRITICAL |
| `CONVERSION_DROP` | Today's rate < 80% of 7-day trailing average | WARN / CRITICAL |
| `DEAD_ZONE` | No `ZONE_ENTER` in past 30 min (during store hours) | INFO / WARN |

Empty `anomalies: []` means no anomalies detected — never an error.

---

## Running Tests

```bash
# Requires a running PostgreSQL test database
export TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/store_intelligence_test

# Run full suite with coverage report
pytest

# Coverage must be ≥70% (enforced by pytest.ini)
```

Or using Docker:

```bash
docker compose exec api pytest
```

Key edge cases covered:

| Test | File |
|------|------|
| Idempotency — same event twice = 1 DB row | `test_ingestion.py` |
| Partial success — malformed events never cause 5xx | `test_ingestion.py` |
| Empty store — all metrics return 0, not error | `test_metrics.py` |
| All-staff clip — `unique_visitors = 0` | `test_metrics.py` |
| Zero purchases — `conversion_rate = 0.0` | `test_metrics.py` |
| Re-entry deduplication — visitor counted once in funnel | `test_funnel.py` |
| Confidence passthrough — low-confidence events accepted | `test_pipeline.py` |
| Dead zone false-positive guard — no alert when store is closed | `test_anomalies.py` |

---

## Project Structure

```
store-intelligence/
├── pipeline/               # Detection pipeline (offline processing)
│   ├── detect.py           # YOLOv9 + ByteTrack person detection
│   ├── tracker.py          # OSNet Re-ID, re-entry, cross-camera dedup
│   ├── zone_classifier.py  # Polygon zone occupancy from store_layout.json
│   ├── staff_classifier.py # Uniform-based staff detection
│   ├── emit.py             # Event assembly + API ingest
│   ├── replay.py           # Replay JSONL for live dashboard
│   └── run.sh              # One command: process all clips
├── app/                    # Intelligence API (FastAPI)
│   ├── main.py             # App factory, middleware, lifespan
│   ├── config.py           # Settings via pydantic-settings
│   ├── db.py               # SQLAlchemy engine + session
│   ├── models.py           # ORM: events, sessions, pos_transactions, baselines
│   ├── schemas.py          # Pydantic: event schema + all response models
│   ├── ingestion.py        # Validate → insert → session reconstruction
│   ├── metrics.py          # /metrics + /heatmap computation
│   ├── funnel.py           # /funnel computation
│   ├── anomalies.py        # Anomaly detection
│   ├── pos_loader.py       # Load pos_transactions.csv at startup
│   ├── middleware.py       # Structured JSON logging
│   ├── exceptions.py       # Global: DB down → 503, no stack traces
│   └── routers/            # Route handlers
│       ├── health.py       # GET /health
│       ├── events.py       # POST /events/ingest
│       └── stores.py       # GET /stores/{id}/metrics|funnel|heatmap|anomalies
├── alembic/                # Database migrations
│   └── versions/
│       └── 001_initial_schema.py
├── tests/                  # Test suite (≥70% coverage enforced)
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DESIGN.md
│   └── CHOICES.md
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh           # Runs migrations then starts uvicorn
├── requirements.txt
├── requirements-pipeline.txt
├── pytest.ini
├── Makefile
└── .env.example
```

---

## Environment Variables

Copy `.env.example` to `.env` and edit as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `localhost` | PostgreSQL host (`postgres` inside Docker) |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `store_intelligence` | Database name |
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | `postgres` | Database password |
| `DB_POOL_SIZE` | `10` | SQLAlchemy connection pool size |
| `APP_VERSION` | `1.0.0` | Included in `/health` response |

---

## Architecture Overview

```
CCTV Clips  →  Detection Pipeline  →  POST /events/ingest  →  PostgreSQL
                  YOLOv9                                          │
                  ByteTrack                                       ├── GET /metrics
                  OSNet Re-ID                                     ├── GET /funnel
                  Zone Classifier                                 ├── GET /heatmap
                  Staff Classifier                                ├── GET /anomalies
                                                                  └── GET /health
POS CSV  ──────────────────────────────── loaded at startup ──────┘
```

See `docs/ARCHITECTURE.md` for the full system design, and `docs/DESIGN.md` for AI-assisted decision documentation.
