#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run.sh — process all CCTV clips and ingest events into the API
#
# Usage:
#   ./pipeline/run.sh                          # all stores, API at localhost:8000
#   ./pipeline/run.sh STORE_BLR_002            # single store
#   ./pipeline/run.sh --no-api                 # write JSONL only
#   ./pipeline/run.sh --api http://remote:8000 # remote API
#
# Prerequisites:
#   pip install -r requirements-pipeline.txt
#   Place clips in data/clips/<STORE_ID>/*.mp4
#   Place store_layout.json in data/
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# ── Defaults ────────────────────────────────────────────────────────────────
API_URL="http://localhost:8000"
NO_API_FLAG=""
STORE_ARG=""

# ── Argument parsing ────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --api)       API_URL="$2"; shift 2 ;;
    --no-api)    NO_API_FLAG="--no-api"; shift ;;
    --*)         echo "Unknown flag: $1"; exit 1 ;;
    *)           STORE_ARG="$1"; shift ;;
  esac
done

# ── Environment ─────────────────────────────────────────────────────────────
if [[ ! -d "data/clips" ]]; then
  echo "ERROR: data/clips/ not found."
  echo "       Place CCTV clips in data/clips/<STORE_ID>/<camera>.mp4"
  exit 1
fi

mkdir -p data/events

echo "============================================================"
echo "  Store Intelligence Detection Pipeline"
echo "  API: ${API_URL:-offline}"
echo "  Clips: data/clips/"
echo "  Output: data/events/"
echo "============================================================"

# ── Run detection ────────────────────────────────────────────────────────────
STORE_FLAG=""
if [[ -n "$STORE_ARG" ]]; then
  STORE_FLAG="--store $STORE_ARG"
fi

python pipeline/detect.py \
  $STORE_FLAG \
  --api "$API_URL" \
  $NO_API_FLAG \
  --clips-dir data/clips \
  --events-dir data/events

echo ""
echo "============================================================"
echo "  Detection complete."
echo "  Event files:"
ls -lh data/events/*.jsonl 2>/dev/null || echo "  (none generated)"
echo ""
echo "  Next steps:"
echo "  • Validate:  head -5 data/events/*.jsonl | python3 -m json.tool"
echo "  • Dashboard: python pipeline/replay.py --speed 10"
echo "  • Metrics:   curl http://localhost:8000/stores/<STORE_ID>/metrics"
echo "============================================================"
