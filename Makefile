.PHONY: up down restart logs shell test coverage migrate lint

# ── Docker ────────────────────────────────────────────────────────────────────

up:
	docker compose up --build -d
	@echo "API → http://localhost:8000/docs"

down:
	docker compose down

restart:
	docker compose restart api

logs:
	docker compose logs -f api

shell:
	docker compose exec api bash

# ── Database ──────────────────────────────────────────────────────────────────

migrate:
	docker compose exec api alembic upgrade head

migrate-local:
	alembic upgrade head

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	pytest

coverage:
	pytest --cov=app --cov-report=html
	@echo "Report → htmlcov/index.html"

# Run a single test file
# Usage: make test-file FILE=tests/test_metrics.py
test-file:
	pytest $(FILE) -v

# ── Pipeline ──────────────────────────────────────────────────────────────────

# Process all clips and emit JSONL events
pipeline:
	./pipeline/run.sh

# Replay generated JSONL into the running API (for live dashboard demo)
replay:
	python pipeline/replay.py

# ── Acceptance gate ───────────────────────────────────────────────────────────

# Verify all 5 acceptance gate criteria from the problem statement
gate:
	@echo "── 1. API health ──────────────────────────────────────────────────"
	curl -sf http://localhost:8000/health | python3 -m json.tool
	@echo ""
	@echo "── 2. POST /events/ingest ─────────────────────────────────────────"
	curl -sf -X POST http://localhost:8000/events/ingest \
	  -H "Content-Type: application/json" \
	  -d '[{"event_id":"00000000-0000-4000-8000-000000000001","store_id":"STORE_BLR_002","camera_id":"CAM_ENTRY_01","visitor_id":"VIS_aaaaaa","event_type":"ENTRY","timestamp":"2026-03-03T10:00:00Z","zone_id":null,"dwell_ms":0,"is_staff":false,"confidence":0.9,"metadata":{"queue_depth":null,"sku_zone":null,"session_seq":1}}]' \
	  | python3 -m json.tool
	@echo ""
	@echo "── 3. GET /stores/STORE_BLR_002/metrics ───────────────────────────"
	curl -sf http://localhost:8000/stores/STORE_BLR_002/metrics | python3 -m json.tool
	@echo ""
	@echo "── 4. GET /stores/STORE_BLR_002/funnel ────────────────────────────"
	curl -sf http://localhost:8000/stores/STORE_BLR_002/funnel | python3 -m json.tool
	@echo ""
	@echo "── 5. GET /stores/STORE_BLR_002/anomalies ─────────────────────────"
	curl -sf http://localhost:8000/stores/STORE_BLR_002/anomalies | python3 -m json.tool
	@echo ""
	@echo "All gate checks passed ✓"
