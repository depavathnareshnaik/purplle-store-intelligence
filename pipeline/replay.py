"""
Real-time replay of a generated JSONL file for the live dashboard (Part E).

Reads events from data/events/<store_id>.jsonl and POSTs them to the API
respecting the original event timestamps — compressed by a configurable
speed multiplier so a 20-minute clip can be replayed in 2 minutes (10×).

This script is the proof that the pipeline and API are genuinely connected,
not just batch-processed once. Run it while the dashboard is open.

Usage:
    # Replay at 10× speed (2 min for a 20-min clip)
    python pipeline/replay.py --store STORE_BLR_002 --speed 10

    # Replay at real-time (20 min)
    python pipeline/replay.py --store STORE_BLR_002 --speed 1

    # Replay all stores
    python pipeline/replay.py --speed 5
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import httpx

logger = logging.getLogger("pipeline.replay")


def replay_store(
    store_id: str,
    events_dir: Path,
    api_url: str,
    speed: float = 10.0,
    batch_size: int = 50,
) -> None:
    """
    Replay events for one store at `speed`× real time.

    Events are sorted by timestamp and grouped into micro-batches.
    Between batches the script sleeps to simulate real-time arrival.
    """
    jsonl_path = events_dir / f"{store_id}.jsonl"
    if not jsonl_path.exists():
        logger.error("No events file for %s at %s", store_id, jsonl_path)
        return

    events = _load_events(jsonl_path)
    if not events:
        logger.warning("Empty events file: %s", jsonl_path)
        return

    events.sort(key=lambda e: e["timestamp"])
    logger.info(
        "Replaying %d events for %s at %.0f× speed → ETA ~%.0f seconds",
        len(events), store_id, speed,
        _duration_seconds(events) / speed,
    )

    # Wall-clock start ≈ first event timestamp mapped to now
    first_event_ts = _parse_ts(events[0]["timestamp"])
    replay_start_wall = time.monotonic()
    replay_start_event = first_event_ts

    batch: List[dict] = []

    for event in events:
        event_ts = _parse_ts(event["timestamp"])
        event_offset_s = (event_ts - replay_start_event).total_seconds()
        target_wall = replay_start_wall + event_offset_s / speed

        batch.append(event)

        if len(batch) >= batch_size:
            # Sleep until the batch's last event time, then flush
            sleep_s = max(0.0, target_wall - time.monotonic())
            if sleep_s > 0:
                time.sleep(sleep_s)
            _post_batch(batch, api_url)
            logger.info(
                "[%s] Posted %d events (latest: %s)",
                store_id, len(batch), event["timestamp"],
            )
            batch.clear()

    if batch:
        _post_batch(batch, api_url)

    logger.info("Replay complete: %s", store_id)


def _load_events(path: Path) -> list:
    events = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def _post_batch(events: list, api_url: str) -> None:
    try:
        resp = httpx.post(f"{api_url}/events/ingest", json=events, timeout=10.0)
        body = resp.json()
        if body.get("rejected", 0):
            logger.warning("Rejected %d events", body["rejected"])
    except Exception as exc:
        logger.warning("POST failed: %s", exc)


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.rstrip("Z")).replace(tzinfo=timezone.utc)


def _duration_seconds(events: list) -> float:
    if len(events) < 2:
        return 0.0
    first = _parse_ts(events[0]["timestamp"])
    last = _parse_ts(events[-1]["timestamp"])
    return max(1.0, (last - first).total_seconds())


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay JSONL events into the API")
    parser.add_argument("--store", help="Specific store ID. Omit to replay all.")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument(
        "--speed", type=float, default=10.0,
        help="Replay speed multiplier (10 = 10× faster than real time)",
    )
    parser.add_argument("--events-dir", default="data/events")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")

    events_dir = Path(args.events_dir)

    if args.store:
        store_ids = [args.store]
    else:
        store_ids = [p.stem for p in sorted(events_dir.glob("*.jsonl"))]

    if not store_ids:
        logger.error("No JSONL files found in %s", events_dir)
        return

    for store_id in store_ids:
        replay_store(
            store_id=store_id,
            events_dir=events_dir,
            api_url=args.api,
            speed=args.speed,
            batch_size=args.batch_size,
        )


if __name__ == "__main__":
    main()
