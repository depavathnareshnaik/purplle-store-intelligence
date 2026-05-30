"""
Event emitter — serialises events to JSONL and optionally POSTs to the API.

Two modes:
  1. JSONL write  — always on; output in data/events/<store_id>.jsonl
  2. API ingest   — optional (config.ingest_to_api); sends batches of 500
                    to POST /events/ingest as events are collected

The file is opened in append mode so that multiple clips for the same store
can be processed sequentially without overwriting earlier output.

BILLING_QUEUE_ABANDON events are resolved post-processing (after all clips
for a store are done) and then flushed to both JSONL and the API.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from pipeline.config import PipelineConfig

logger = logging.getLogger("pipeline.emit")


class EventEmitter:
    def __init__(self, config: PipelineConfig, store_id: str):
        self.config = config
        self.store_id = store_id

        config.events_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = config.events_dir / f"{store_id}.jsonl"

        self._buffer: List[dict] = []
        self._total_emitted: int = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def add(self, event: dict) -> None:
        """Add a single event to the buffer."""
        self._buffer.append(event)
        if len(self._buffer) >= self.config.ingest_batch_size:
            self.flush()

    def add_many(self, events: List[dict]) -> None:
        for e in events:
            self.add(e)

    def flush(self) -> None:
        """Write buffered events to JSONL and (optionally) POST to API."""
        if not self._buffer:
            return

        self._write_jsonl(self._buffer)

        if self.config.ingest_to_api:
            self._post_batch(self._buffer)

        self._total_emitted += len(self._buffer)
        logger.info(
            "Flushed %d events for %s (total so far: %d)",
            len(self._buffer), self.store_id, self._total_emitted,
        )
        self._buffer.clear()

    def close(self) -> None:
        """Flush any remaining events and log summary."""
        self.flush()
        logger.info("Emitter closed. Total events emitted: %d", self._total_emitted)

    # ── JSONL write ────────────────────────────────────────────────────────────

    def _write_jsonl(self, events: List[dict]) -> None:
        with open(self.output_path, "a", encoding="utf-8") as fh:
            for event in events:
                fh.write(json.dumps(event) + "\n")

    # ── API POST ───────────────────────────────────────────────────────────────

    def _post_batch(self, events: List[dict]) -> None:
        url = f"{self.config.api_url}/events/ingest"
        try:
            resp = httpx.post(url, json=events, timeout=30.0)
            body = resp.json()
            if body.get("rejected", 0) > 0:
                logger.warning(
                    "API rejected %d events — first error: %s",
                    body["rejected"],
                    body["errors"][0] if body["errors"] else "unknown",
                )
        except httpx.ConnectError:
            logger.warning(
                "API not reachable at %s — events written to JSONL only. "
                "Run: python pipeline/emit.py --replay-store %s",
                url, self.store_id,
            )
        except Exception as exc:
            logger.error("Unexpected error POSTing to API: %s", exc)


# ---------------------------------------------------------------------------
# POS transaction loader (used by tracker.resolve_abandons)
# ---------------------------------------------------------------------------

def load_pos_transactions(config: PipelineConfig) -> List[Dict[str, Any]]:
    """
    Load pos_transactions.csv into a list of dicts.
    Returns an empty list if the file does not exist.
    """
    path = config.pos_path
    if not path.exists():
        logger.warning("pos_transactions.csv not found — BILLING_QUEUE_ABANDON detection disabled")
        return []

    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append({
                "store_id": row["store_id"].strip(),
                "transaction_id": row["transaction_id"].strip(),
                "timestamp": row["timestamp"].strip(),
                "basket_value_inr": float(row["basket_value_inr"].strip()),
            })
    logger.info("Loaded %d POS transactions", len(rows))
    return rows


# ---------------------------------------------------------------------------
# CLI replay: ingest an existing JSONL file into the running API
# ---------------------------------------------------------------------------

def replay_jsonl(jsonl_path: Path, api_url: str, batch_size: int = 500) -> None:
    """
    POST events from a JSONL file to the API in batches.
    Used when the pipeline ran in offline mode (ingest_to_api=False)
    or to re-ingest after the API was reset.
    """
    events: List[dict] = []
    total = 0

    with open(jsonl_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed JSONL line: %s", exc)
                continue

            if len(events) >= batch_size:
                _post_once(events, api_url)
                total += len(events)
                events.clear()

    if events:
        _post_once(events, api_url)
        total += len(events)

    logger.info("Replayed %d events from %s", total, jsonl_path)


def _post_once(events: List[dict], api_url: str) -> None:
    url = f"{api_url}/events/ingest"
    resp = httpx.post(url, json=events, timeout=60.0)
    body = resp.json()
    logger.info("Ingested %d, rejected %d", body.get("accepted", 0), body.get("rejected", 0))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Replay a JSONL event file into the API")
    parser.add_argument("jsonl", help="Path to JSONL file")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    replay_jsonl(Path(args.jsonl), args.api, args.batch_size)
