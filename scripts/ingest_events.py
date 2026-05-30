#!/usr/bin/env python3
"""
Ingest all generated JSONL event files into the running API.

Usage:
  python scripts/ingest_events.py                         # all stores
  python scripts/ingest_events.py STORE_BLR_002           # single store
  python scripts/ingest_events.py --api http://host:8000  # remote API
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT       = Path(__file__).parent.parent
EVENTS_DIR = ROOT / "data" / "events"

BATCH_SIZE = 500


def ingest_file(jsonl_path: Path, api_url: str) -> None:
    events = []
    total_accepted = 0
    total_rejected = 0

    with open(jsonl_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

            if len(events) >= BATCH_SIZE:
                accepted, rejected = _post(events, api_url)
                total_accepted += accepted
                total_rejected += rejected
                events.clear()

    if events:
        accepted, rejected = _post(events, api_url)
        total_accepted += accepted
        total_rejected += rejected

    status = "✓" if total_rejected == 0 else "⚠"
    print(f"  {status} {jsonl_path.name:<30} accepted={total_accepted}  rejected={total_rejected}")


def _post(events: list, api_url: str) -> tuple[int, int]:
    url = f"{api_url}/events/ingest"
    try:
        resp = httpx.post(url, json=events, timeout=30.0)
        body = resp.json()
        return body.get("accepted", 0), body.get("rejected", 0)
    except httpx.ConnectError:
        print(f"\n  ERROR: Cannot connect to {url}")
        print("  Is the API running?  →  docker compose up --build\n")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest JSONL events into the API")
    parser.add_argument("store", nargs="?", help="Specific store ID (default: all)")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()

    print(f"\n  Ingesting events → {args.api}\n")

    if args.store:
        files = [EVENTS_DIR / f"{args.store}.jsonl"]
    else:
        files = sorted(EVENTS_DIR.glob("*.jsonl"))

    if not files or not any(f.exists() for f in files):
        print("  No JSONL files found.")
        print("  Run:  python scripts/generate_dataset.py\n")
        sys.exit(1)

    for f in files:
        if f.exists():
            ingest_file(f, args.api)

    print(f"\n  Done. Check metrics:")
    print(f"  curl -s {args.api}/stores/STORE_BLR_002/metrics | python3 -m json.tool\n")


if __name__ == "__main__":
    main()
