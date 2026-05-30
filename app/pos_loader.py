"""
POS transaction loader.

Handles two CSV formats:
  1. Real Purplle format (Brigade_Bangalore_10_April_26.csv):
       order_id, order_date (DD-MM-YYYY), order_time (HH:MM:SS),
       store_id (ST1008), total_amount, invoice_type, ...

  2. Simple synthetic format:
       store_id, transaction_id, timestamp (ISO-8601), basket_value_inr

Auto-detects format from column headers.
Safe to call on every restart — ON CONFLICT DO NOTHING prevents duplicates.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import SessionLocal
from app.models import POSTransaction

logger = logging.getLogger("api.pos_loader")

POS_CSV_PATH = Path("data/pos_transactions.csv")
BATCH_SIZE = 500

# Map real Purplle store IDs → our internal store IDs
STORE_ID_MAP = {
    "ST1008": "STORE_BLR_002",
    "ST1009": "STORE_BLR_001",
    "ST1010": "STORE_DEL_001",
}


def load_pos_transactions() -> int:
    if not POS_CSV_PATH.exists():
        logger.warning(
            '{"message": "pos_transactions.csv not found", "path": "%s", '
            '"effect": "conversion_rate will be 0 until file is loaded"}',
            POS_CSV_PATH,
        )
        return 0

    rows = _read_csv(POS_CSV_PATH)
    if not rows:
        logger.warning('{"message": "pos_transactions.csv is empty or has no valid rows"}')
        return 0

    inserted = _bulk_insert(rows)
    logger.info(
        '{"message": "POS transactions loaded", "total_rows": %d, "inserted": %d}',
        len(rows), inserted,
    )
    return inserted


def _read_csv(path: Path) -> List[dict]:
    rows: List[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []

        # Detect format
        is_purplle_format = "order_id" in headers and "order_date" in headers

        for line_num, row in enumerate(reader, start=2):
            try:
                parsed = _parse_purplle_row(row) if is_purplle_format else _parse_simple_row(row)
                if parsed:
                    rows.append(parsed)
            except Exception as exc:
                logger.warning(
                    '{"message": "skipping malformed POS row", "line": %d, "reason": "%s"}',
                    line_num, str(exc)[:100],
                )
    return rows


def _parse_purplle_row(row: dict) -> dict | None:
    """Parse the real Purplle POS export format."""
    # Skip returns
    if row.get("invoice_type", "").strip().lower() == "return":
        return None

    # Skip zero-value line items (e.g. free carry bags with amount=0)
    try:
        total = float(row.get("total_amount", "0").strip() or "0")
    except ValueError:
        total = 0.0

    # Use order_id + sku as the unique transaction identifier
    # (one order can have multiple line items — we deduplicate later)
    order_id = row.get("order_id", "").strip()
    sku = row.get("sku", "").strip()
    transaction_id = f"{order_id}_{sku}" if sku else order_id

    store_id_raw = row.get("store_id", "").strip()
    store_id = STORE_ID_MAP.get(store_id_raw, store_id_raw)

    # Parse date + time → UTC datetime
    # Date format: DD-MM-YYYY   Time format: HH:MM:SS   Timezone: IST (UTC+5:30)
    date_str = row.get("order_date", "").strip()
    time_str = row.get("order_time", "").strip()
    if not date_str or not time_str:
        return None

    try:
        # Parse as IST (UTC+5:30) then convert to UTC
        dt_naive = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M:%S")
        # IST = UTC + 5:30, so subtract 5:30 to get UTC
        from datetime import timedelta
        dt_utc = dt_naive.replace(tzinfo=timezone.utc) - timedelta(hours=5, minutes=30)
    except ValueError as e:
        raise ValueError(f"Cannot parse date/time '{date_str} {time_str}': {e}")

    return {
        "transaction_id": transaction_id,
        "store_id":        store_id,
        "timestamp":       dt_utc,
        "basket_value_inr": total,
    }


def _parse_simple_row(row: dict) -> dict | None:
    """Parse our synthetic/simple CSV format."""
    raw_ts = row.get("timestamp", "").strip()
    if not raw_ts:
        return None

    if raw_ts.endswith("Z"):
        raw_ts = raw_ts[:-1] + "+00:00"
    ts = datetime.fromisoformat(raw_ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    return {
        "transaction_id":  row.get("transaction_id", "").strip(),
        "store_id":        row.get("store_id", "").strip(),
        "timestamp":       ts,
        "basket_value_inr": float(row.get("basket_value_inr", "0").strip() or "0"),
    }


def _bulk_insert(rows: List[dict]) -> int:
    total_inserted = 0
    db = SessionLocal()
    try:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i: i + BATCH_SIZE]
            result = db.execute(
                pg_insert(POSTransaction)
                .values(batch)
                .on_conflict_do_nothing(index_elements=["transaction_id"])
            )
            total_inserted += result.rowcount
        db.commit()
    finally:
        db.close()
    return total_inserted
