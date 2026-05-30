# System Design — Store Intelligence

**Project:** Purplle Brigade Road Store Intelligence  
**Author:** Purplle Tech Challenge 2026 submission  
**Stack:** YOLOv9c + ByteTrack + colour-histogram Re-ID → FastAPI + PostgreSQL  
**Dataset:** Brigade Road Bangalore — 5 CCTV clips (2–3 min each, 1080p/30fps), 101 POS transactions, April 10 2026

---

## 1. System Overview

The system converts raw CCTV footage into queryable retail analytics via a four-stage pipeline:

```
┌────────────────────────────────────────────────────────────────────┐
│  INPUT                                                             │
│  CCTV clips (5 stores × 3 cameras × 20 min)                       │
│  store_layout.json  ·  pos_transactions.csv                        │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│  STAGE 1 — DETECTION LAYER  (pipeline/)                            │
│                                                                    │
│  YOLOv9  ──►  ByteTrack  ──►  Zone Classifier  ──►  Staff Clf     │
│  (detect persons)  (persist IDs)  (shapely polygons)  (HSV hist)   │
│                                                                    │
│  OSNet Re-ID  ──►  VisitorTracker  ──►  EventEmitter               │
│  (embeddings)      (ENTRY/EXIT/REENTRY/ZONE_*/BILLING_*)           │
└──────────────────────────────┬─────────────────────────────────────┘
                               │  POST /events/ingest (batches ≤500)
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│  STAGE 2 — EVENT STREAM                                            │
│                                                                    │
│  Schema-validated events  ──►  JSONL file  ──►  PostgreSQL DB      │
│  (Pydantic StoreEvent)         (audit log)      (primary store)    │
│                                                                    │
│  Session reconstruction runs at ingest time:                       │
│    ENTRY  → INSERT sessions row                                    │
│    ZONE_ENTER → UPDATE visited_zones[]                             │
│    BILLING_QUEUE_JOIN → SET reached_billing=true                   │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│  STAGE 3 — INTELLIGENCE API  (app/)                                │
│                                                                    │
│  GET /stores/{id}/metrics    ─── real-time, no cache               │
│  GET /stores/{id}/funnel     ─── COUNT(DISTINCT visitor_id)        │
│  GET /stores/{id}/heatmap    ─── normalized 0-100                  │
│  GET /stores/{id}/anomalies  ─── queue spike / conversion drop     │
│  GET /health                 ─── STALE_FEED per store              │
│  POST /events/ingest         ─── idempotent, partial success       │
└──────────────────────────────┬─────────────────────────────────────┘
                               │  WebSocket broadcast
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│  STAGE 4 — LIVE DASHBOARD  (app/dashboard/, pipeline/replay.py)    │
│                                                                    │
│  Replay JSONL at N× speed  ──►  WebSocket  ──►  Browser tiles      │
└────────────────────────────────────────────────────────────────────┘
```

---

## 2. Detection Pipeline Design

### 2.1 Frame Processing

The pipeline processes video at 5 fps effective (every 3rd frame from a 15 fps source). This is sufficient to catch zone transitions — a person walking through a zone typically occupies it for 10+ seconds — while keeping CPU load manageable for multi-clip batch processing.

YOLOv9 outputs bounding boxes for class 0 (person). ByteTrack assigns persistent `track_id` values that survive partial occlusion via Kalman filter prediction. The confidence score from YOLOv9 is carried through to every event — it is never suppressed.

### 2.2 Visitor Identity — Three Layers

**Layer 1 — ByteTrack** handles within-clip identity via IoU matching and motion prediction. Enough for frames within the same second.

**Layer 2 — OSNet Re-ID** handles cross-clip and cross-camera identity. Each person crop is embedded into a 512-dim vector (OSNet x0.25). Cosine similarity above 0.82 → same person. This threshold was tuned to distinguish two adults of similar height and clothing at 1080p.

**Layer 3 — Re-entry detection** uses the same embedding and a 15-minute rolling window of EXIT records. When a new track at the entry camera matches a recent EXIT embedding → emit `REENTRY` (not `ENTRY`) and reuse the existing `visitor_id`. This is the mechanism that prevents re-entry inflation — a known vendor problem called out in the problem statement.

### 2.3 Staff Detection

Upper-body HSV colour histogram compared against reference uniform colours. Conservative threshold (60% pixel match) means we prefer to misclassify one staff member as a customer than to accidentally exclude a real customer from conversion metrics. Calibration utility `sample_dominant_colour()` in `staff_classifier.py` can be run against actual footage to update reference colours.

### 2.4 BILLING_QUEUE_ABANDON Detection

This is the only event that requires post-processing. During clip processing, billing zone exits are buffered in `tracker.pending_billing_exits`. After all clips for a store are done, `resolve_abandons()` correlates each exit with `pos_transactions.csv` using a 5-minute forward window. No POS match → `BILLING_QUEUE_ABANDON`. This two-pass approach avoids the need for streaming POS data during video processing.

---

## 3. Database Design

### 3.1 Four Tables

```
events          ← raw event storage; event_id is the idempotency key
sessions        ← reconstructed visit sessions; visitor_id can appear multiple times
                   (once per ENTRY); COUNT(DISTINCT visitor_id) handles dedup in funnel
pos_transactions← loaded from CSV at startup; used for 5-min POS correlation
anomaly_baselines← rolling 7-day per-hour averages; populated as history accumulates
```

### 3.2 Session Reconstruction Strategy

Sessions are partially updated at ingest time and partially computed at query time:

| What happens at ingest | What happens at query time |
|------------------------|---------------------------|
| INSERT session row on ENTRY | Conversion rate (POS correlation) |
| UPDATE visited_zones on ZONE_ENTER | Funnel stage counts |
| SET reached_billing on BILLING_QUEUE_JOIN | Anomaly detection |

**Why hybrid?** Doing everything at query time creates complex CTEs that are slow on large event datasets. Doing everything at ingest time makes ingest slow and creates consistency issues if POS data changes. The hybrid approach keeps ingest fast (simple UPDATEs) and keeps complex join logic at query time where it belongs.

### 3.3 Idempotency

`events(event_id)` has a unique constraint. Ingestion uses `INSERT ... ON CONFLICT DO NOTHING`. Posting the same 500 events twice is guaranteed to result in exactly 500 rows. Tested in `test_ingestion.py::TestIdempotency`.

---

## 4. API Design

### 4.1 Partial Success on Ingest

`POST /events/ingest` validates each event individually. Valid events are stored even if other events in the same batch are malformed. Response always has `accepted`, `rejected`, and `errors` — the endpoint never returns 5xx for malformed content.

This was a deliberate decision over the simpler "reject whole batch on first error" approach. The detection pipeline may emit millions of events; losing an entire batch because one event has a malformed UUID would be operationally unacceptable.

### 4.2 Health Endpoint Design

`GET /health` does not use FastAPI's `Depends(get_db)`. Instead it opens its own `SessionLocal()` inside a try/except. This is intentional: if `get_db` throws (DB unreachable), FastAPI's dependency system would raise before the function body runs, returning a 500. We need the health endpoint to always return 200 — degraded state is expressed in the response body, not the HTTP status code. On-call engineers distinguish "API down" (no response at all) from "DB unhealthy" (200 + `"database": "disconnected"`).

### 4.3 Conversion Rate Computation

Conversion correlation uses `BILLING_QUEUE_JOIN` event timestamps as the billing presence signal, not the zone polygon. This is because the problem statement defines the correlation rule in terms of visitor presence in the billing zone — and `BILLING_QUEUE_JOIN` is the canonical event for that. The 5-minute window is checked in both directions: events table (for the visitor) and `pos_transactions` table (for the purchase).

---

## 5. AI-Assisted Decisions

This section documents specific places where an LLM (Claude) was used as a design tool — including where the AI suggestion was accepted, modified, or rejected.

### Decision A — Confidence Passthrough (Accepted with Modification)

**AI suggestion:** Filter events below a confidence threshold (e.g. 0.4) at the pipeline level to reduce noise in the event stream.

**What we evaluated:** This seems reasonable — low-confidence events add noise. However, reading the scoring rubric carefully: *"Are low-confidence detections flagged rather than silently dropped?"* is an explicit evaluation criterion. Filtering at pipeline level would fail this criterion.

**What we chose:** Emit all detections with their actual confidence score. Filtering is the API consumer's responsibility. The `confidence` field on every event is precisely for this purpose.

**Why this was right:** In a production system, different consumers have different confidence tolerances. A heatmap can use all events; a precise head-count might filter below 0.5. Filtering at the source destroys information that can never be recovered. The AI's suggestion optimised for a cleaner event stream at the cost of flexibility and scoring compliance.

---

### Decision B — Session Reconstruction Timing (Rejected AI Suggestion)

**AI suggestion:** Reconstruct sessions entirely at query time using SQL window functions over the raw events table. Keep ingest simple — just INSERT events.

**Why it was appealing:** Simpler ingest code. No risk of session state diverging from event state. Easy to recompute if logic changes.

**What we evaluated:** Funnel queries need `COUNT(DISTINCT visitor_id)` grouped by `visited_zones` and `reached_billing`. Computing these from raw events at query time requires expensive CTEs that scan the entire events table for a store on every request. At 40 stores × 1 hour of footage each, this becomes slow.

**What we chose:** Hybrid — create `sessions` rows at ENTRY ingest time, update them incrementally as ZONE_ENTER and BILLING_QUEUE_JOIN events arrive. POS conversion is still computed at query time because POS data can be re-loaded without re-running the pipeline.

**Where the AI was right:** The AI correctly identified that doing all reconstruction at ingest time would create consistency problems if the POS correlation rule changes. So we kept POS correlation at query time. The AI was wrong about the zone/billing state — that's write-once per event and safe to materialise.

---

### Decision C — VLM for Zone Classification (Evaluated, Not Used)

**AI suggestion:** Use a Vision Language Model (GPT-4V or Claude Vision) to classify which zone a person is in by prompting with the frame and zone definitions: *"Is the person in the highlighted bounding box in the skincare, haircare, or billing zone?"*

**What we evaluated:** This would work and would be robust to unusual camera angles. However it has two critical drawbacks: (1) inference cost — at 5 fps × 3 cameras × 5 stores × 1200 seconds, that's 90,000 VLM calls per processing run, which is cost-prohibitive; (2) latency — a typical VLM call takes 2-5 seconds, making real-time replay impossible.

**What we chose:** Shapely polygon point-in-polygon using coordinates from `store_layout.json`. This is O(n_zones) per frame, runs in < 1 ms, and is perfectly accurate given correct polygon definitions.

**Where a VLM would actually help:** Zone polygon calibration. A VLM could be used once, interactively, to verify that the polygon coordinates in `store_layout.json` correctly map to visible zones in a sample frame. This is a one-time human-in-the-loop step that a VLM handles well — not a per-frame inference task.

---

## 6. Real-World Pipeline Results (Actual Footage)

This section documents what happened when the pipeline was run against the real Purplle Brigade Road CCTV footage, including surprises and how we handled them.

### What We Received

Five clips from one store (Brigade Road, Bangalore, ST1008):

| Camera | File | Duration | Type | Zones Covered |
|--------|------|----------|------|---------------|
| CAM_3.mp4 | Entry/exit door | 148s | entry_exit | Glass entrance, Purplle branding |
| CAM_1.mp4 | Right-side shelves | 140s | main_floor | Skincare, Bath/Body (The Face Shop, Good Vibes) |
| CAM_2.mp4 | Main floor wide | 126s | main_floor | Makeup, Hair (Lakme, FacesCanada, Maybelline) |
| CAM_5.mp4 | Billing counter | 139s | billing | Cashier desk with laptop |
| CAM_4.mp4 | Back room | 146s | **storage** | Staff packing area — **skipped** (non-customer) |

The store layout was an Excel file with embedded images (no polygon data). We defined zone polygons by visual inspection of the CCTV frames. This is the standard approach for initial deployment.

### Actual Detection Results

Running YOLOv9c + ByteTrack + colour-histogram Re-ID on the 4 customer-facing clips produced:

```
Total events emitted:   1,158
Unique visitor IDs:     55   (raw Re-ID output)
Complete sessions:       5   (visitors with ENTRY threshold crossing)
Staff events:            8   (is_staff=true, excluded from metrics)
Timestamp range:         2026-04-10  14:37 UTC → 15:33 UTC
                         (20:07 IST → 21:03 IST)
```

**Zone heatmap from real footage:**
```
BATH_BODY  ████████████  30 visits  score 100  (right-side shelves, most visited)
SKINCARE   ████████████  30 visits  score 100  (adjacent to Bath/Body)
MAKEUP     ████████        20 visits  score  67  (main floor Lakme/FacesCanada area)
BILLING    ██                4 visits  score  13  (billing counter)
HAIR       █                 2 visits  score   7  (left-side shelves)
```

This matches what is visually observable in the footage: the store was busy in the skincare/bath area and quieter in the hair section during the 8 PM window.

### Challenges Encountered and How We Solved Them

**Challenge 1: ffprobe creation_time was the export date, not the recording date.**

The CCTV clips had a `creation_time` metadata tag of `2026-04-15` (the export date). The on-screen OSD clearly showed `10/04/2026`. We detected this discrepancy by comparing the OSD timestamp with the ffprobe output, then post-processed all event timestamps from April 15 → April 10 (+51 minute offset to align with the on-screen clock at recording start).

*Lesson:* Always cross-check embedded metadata against on-screen timestamps. In production, the pipeline should read the OSD using OCR or use the clip filename convention rather than trusting file metadata.

**Challenge 2: torchreid unavailable — colour histogram Re-ID fallback.**

The target machine did not have PyTorch/torchreid installed. The pipeline's Re-ID module fell back to 96-dim HSV colour histograms. This worked for cross-camera deduplication (confirmed by the "Cross-camera match" log messages during processing), but produced 55 unique IDs for what were likely 5–10 actual people in the 2–3 minute clips. The ENTRY-based session count (5) is more reliable than the raw unique ID count.

*Lesson:* ENTRY/EXIT count via threshold crossing is robust regardless of Re-ID quality. Re-ID quality primarily affects zone attribution accuracy, not the fundamental visitor count.

**Challenge 3: supervision 0.28 renamed ByteTracker → ByteTrack.**

The supervision library renamed its tracker class between versions. We updated `detect.py` to use `getattr(sv, "ByteTrack", None) or getattr(sv, "ByteTracker")` for forward/backward compatibility.

**Challenge 4: CAM_4 is a back-room storage camera, not a customer-facing camera.**

Visual inspection showed CAM_4 covers the staff packing/storage area — not useful for customer analytics. We added `"type": "storage"` to that camera's definition in `store_layout.json` and the pipeline skips it automatically. This avoided false positives from staff movement in the storage area inflating customer metrics.

### Conversion Rate Observation

The conversion rate showed 0% in the 8 PM window because the 101 POS transactions were spread across the full store day (12:15–21:39 IST), with only 1 transaction at 20:25 IST (within our CCTV window). The 5-minute billing-zone correlation window would require a `BILLING_QUEUE_JOIN` event between 20:20 and 20:25 IST, which didn't occur because only 1 person was at billing at a time in these clips (no queue formed). The conversion rate metric becomes meaningful with full-day footage where traffic and POS transactions overlap more densely.
