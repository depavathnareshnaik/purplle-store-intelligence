# Submission Checklist — Purplle Tech Challenge 2026, Round 2

**Candidate:** depavath.naresh@provakil.com  
**Store:** Brigade Road, Bangalore (ST1008 / STORE_BLR_002)  
**Dataset date:** April 10, 2026

---

## 5.2 Acceptance Gate — All 5 Must Pass

| # | Gate Item | Status | Evidence |
|---|-----------|--------|---------|
| 1 | `docker compose up` starts API — no manual steps beyond `git clone` | ✅ **PASS** | `entrypoint.sh` runs migrations + uvicorn automatically |
| 2 | README explains how to run detection pipeline against clips and where output goes | ✅ **PASS** | README.md → "Running Detection Pipeline" section + Quick Start step 4 |
| 3 | `POST /events/ingest` accepts events without 5xx response | ✅ **PASS** | 10/10 assertions pass; always returns 200 |
| 4 | `GET /stores/STORE_BLR_002/metrics` returns valid JSON | ✅ **PASS** | Returns real data from actual footage |
| 5 | `DESIGN.md` and `CHOICES.md` both exist and are non-trivial (>250 words each) | ✅ **PASS** | DESIGN.md: ~1,900 words; CHOICES.md: ~1,700 words |

---

## 7.2 Full Submission Checklist

### Repository

- [ ] Git repository created (private)
- [ ] Reviewer handle invited as collaborator
- [ ] All code committed and pushed
- [ ] `docker compose up` tested on clean machine before submission

### Code & Structure

- [x] `pipeline/detect.py` — main detection + tracking
- [x] `pipeline/tracker.py` — Re-ID / tracking logic
- [x] `pipeline/emit.py` — event schema + emission
- [x] `pipeline/run.sh` — one command to process all clips → events
- [x] `app/main.py` — FastAPI entrypoint
- [x] `app/models.py` — Pydantic + SQLAlchemy event schema
- [x] `app/ingestion.py` — ingest, dedup
- [x] `app/metrics.py` — real-time metric computation
- [x] `app/funnel.py` — funnel + session logic
- [x] `app/anomalies.py` — anomaly detection
- [x] `app/routers/health.py` — GET /health
- [x] `docker-compose.yml` — services: api + postgres
- [x] `README.md` — setup in 5 commands

### Tests

- [x] `tests/test_pipeline.py` — prompt block header ✓
- [x] `tests/test_metrics.py` — prompt block header ✓
- [x] `tests/test_funnel.py` — prompt block header ✓
- [x] `tests/test_ingestion.py` — prompt block header ✓
- [x] `tests/test_anomalies.py` — prompt block header ✓
- [x] `tests/test_health.py` — prompt block header ✓
- [x] Statement coverage: **85%** (requirement: >70%)
- [x] Edge cases covered: empty store, all-staff, zero purchases, re-entry in funnel

### Documentation

- [x] `docs/DESIGN.md` — architecture + "AI-Assisted Decisions" section (3 examples)
- [x] `docs/CHOICES.md` — 3 decisions with full reasoning + real performance data
- [x] Prompt blocks in ALL test files (`# PROMPT: ... / # CHANGES MADE: ...`)
- [x] Dashboard URL in README: `http://localhost:8000/dashboard`

---

## Scoring Projection

| Part | Dimension | Max | Expected | Notes |
|------|-----------|-----|---------|-------|
| A | Entry/exit count accuracy | 10 | 6–8 | Pipeline ran on real footage; 10 ENTRY events in 2-3 min clips |
| A | Staff exclusion, re-entry, group handling | 10 | 7–9 | Staff correctly flagged; re-entry implemented; group entry via NMS |
| A | Schema compliance and event quality | 10 | 9–10 | 1158 real events, all schema-compliant, 0 rejected |
| B | API endpoint correctness | 20 | 18–20 | 10/10 assertions pass |
| B | Funnel accuracy and session deduplication | 10 | 8–10 | COUNT(DISTINCT visitor_id); re-entry = 1 visitor |
| B | Anomaly detection correctness | 5 | 4–5 | Queue spike, conversion drop, dead zone implemented |
| C | Containerisation + README | 5 | 5 | docker compose up works; README 5 commands |
| C | Structured logs + health endpoint | 5 | 5 | trace_id, latency_ms, event_count logged; STALE_FEED implemented |
| C | Test coverage and edge cases | 10 | 9–10 | 85% coverage; 105 tests pass |
| D | AI usage depth | 15 | 12–14 | CHOICES.md with real iteration; DESIGN.md real-world observations |
| E | Live dashboard bonus | +10 | +8–10 | WebSocket + Chart.js + replay.py |
| **Total** | | **100+10** | **91–101** | |

---

## How to Run Everything — Final Verification

### Step 1: Start the system

```bash
cd store-intelligence
cp .env.example .env
docker compose up --build -d
# Wait for: Application startup complete.
```

### Step 2: Run the detection pipeline

```bash
# Install pipeline dependencies
pip install -r requirements-pipeline.txt

# Process CCTV clips (place in data/clips/STORE_BLR_002/)
./pipeline/run.sh

# Ingest events into API
pip install httpx
python3 scripts/ingest_events.py
```

### Step 3: Verify all endpoints

```bash
# Health check
curl http://localhost:8000/health

# Metrics (real data)
curl http://localhost:8000/stores/STORE_BLR_002/metrics

# Funnel
curl http://localhost:8000/stores/STORE_BLR_002/funnel

# Heatmap
curl http://localhost:8000/stores/STORE_BLR_002/heatmap

# Anomalies
curl http://localhost:8000/stores/STORE_BLR_002/anomalies

# Run all 10 scoring assertions
python3 data/assertions.py
```

### Step 4: Live dashboard

```
http://localhost:8000/dashboard
```

For live metrics replay:
```bash
python3 pipeline/replay.py --store STORE_BLR_002 --speed 5
```

### Step 5: Run tests

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/store_intelligence_test \
  python3 -m pytest tests/ -q
# Expected: 105 passed, 85% coverage
```

---

## What the Real Data Showed

Running the pipeline on the actual Brigade Road footage (April 10, 2026, 20:07–21:03 IST):

- **5 complete visitor sessions** (unique customers who crossed entry threshold)
- **8 staff events** correctly flagged and excluded from metrics
- **1,158 total events** across 4 cameras
- **Top zone:** BATH_BODY + SKINCARE (score 100 each) — the right-side product shelves were most visited
- **Processing time:** ~12 minutes on CPU (4 cameras × ~3 minutes each)
- **Model:** YOLOv9c (49.4MB) — auto-downloaded by ultralytics
- **Re-ID:** Colour-histogram fallback (torchreid not available) — cross-camera deduplication still worked

---

## What's in the Repository

```
store-intelligence/
├── pipeline/           Detection pipeline (YOLOv9c + ByteTrack + Re-ID)
├── app/                Intelligence API (FastAPI + PostgreSQL)
├── tests/              105 tests, 85% coverage
├── docs/
│   ├── DESIGN.md       Architecture + AI-Assisted Decisions + real results
│   ├── CHOICES.md      3 decisions + actual measured performance
│   └── ARCHITECTURE.md Full system architecture documentation
├── data/
│   ├── store_layout.json      Real Purplle Brigade Road zone definitions
│   ├── pos_transactions.csv   101 real POS transactions (April 10, 2026)
│   └── events/
│       └── STORE_BLR_002.jsonl  1,158 real detection events
├── scripts/
│   ├── generate_dataset.py    Synthetic data generator (testing only)
│   └── ingest_events.py       Batch ingest JSONL → API
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
├── README.md
└── pytest.ini
```
