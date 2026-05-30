#!/usr/bin/env python3
"""
Generate synthetic dataset for testing the Store Intelligence system.

Produces files with TODAY's timestamps so all API "today" filters work.

Output:
  data/pos_transactions.csv          - POS records for today
  data/events/STORE_BLR_002.jsonl   - full event stream (primary store)
  data/events/STORE_DEL_001.jsonl   - second store (for multi-store testing)
  data/events/STORE_MUM_001.jsonl   - third store
  data/sample_events.jsonl           - first 200 events (schema reference)

Usage:
  cd store-intelligence
  python scripts/generate_dataset.py
"""

import csv
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)   # reproducible runs

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
DATA_DIR   = ROOT / "data"
EVENTS_DIR = DATA_DIR / "events"
EVENTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Time helpers ──────────────────────────────────────────────────────────────
NOW   = datetime.now(timezone.utc)
TODAY = NOW.replace(hour=0, minute=0, second=0, microsecond=0)

def ts(hours: float, minutes: float = 0, seconds: float = 0) -> datetime:
    """Return a datetime at TODAY 10:00 + offset."""
    base = TODAY.replace(hour=10, minute=0, second=0, microsecond=0)
    return base + timedelta(hours=hours, minutes=minutes, seconds=seconds)

def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def eid() -> str:
    return str(uuid.uuid4())

def vid() -> str:
    return f"VIS_{uuid.uuid4().hex[:6]}"


# ── Event builder ─────────────────────────────────────────────────────────────

class Session:
    """Builds a realistic visitor session as a list of events."""

    def __init__(self, store_id: str, camera_entry: str, camera_floor: str,
                 camera_bill: str, visitor_id: str = None, is_staff: bool = False):
        self.store_id      = store_id
        self.cam_entry     = camera_entry
        self.cam_floor     = camera_floor
        self.cam_bill      = camera_bill
        self.visitor_id    = visitor_id or vid()
        self.is_staff      = is_staff
        self.events: list  = []
        self._seq          = 0

    def _seq_next(self) -> int:
        self._seq += 1
        return self._seq

    def _evt(self, camera_id, event_type, dt, zone_id=None, dwell_ms=0,
             queue_depth=None, sku_zone=None, confidence=None):
        if confidence is None:
            confidence = round(random.uniform(0.72, 0.96), 2)
        self.events.append({
            "event_id":  eid(),
            "store_id":  self.store_id,
            "camera_id": camera_id,
            "visitor_id": self.visitor_id,
            "event_type": event_type,
            "timestamp":  fmt(dt),
            "zone_id":    zone_id,
            "dwell_ms":   dwell_ms,
            "is_staff":   self.is_staff,
            "confidence": confidence,
            "metadata": {
                "queue_depth": queue_depth,
                "sku_zone":    sku_zone,
                "session_seq": self._seq_next(),
            },
        })
        return dt

    # ── Convenience methods ───────────────────────────────────────────────────

    def entry(self, dt):
        return self._evt(self.cam_entry, "ENTRY", dt)

    def exit(self, dt):
        return self._evt(self.cam_entry, "EXIT", dt)

    def reentry(self, dt):
        return self._evt(self.cam_entry, "REENTRY", dt)

    def zone_enter(self, dt, zone_id, sku_zone):
        return self._evt(self.cam_floor, "ZONE_ENTER", dt, zone_id=zone_id, sku_zone=sku_zone)

    def zone_dwell(self, dt, zone_id, sku_zone, dwell_ms=30000):
        return self._evt(self.cam_floor, "ZONE_DWELL", dt, zone_id=zone_id,
                         dwell_ms=dwell_ms, sku_zone=sku_zone)

    def zone_exit(self, dt, zone_id, sku_zone, dwell_ms=0):
        return self._evt(self.cam_floor, "ZONE_EXIT", dt, zone_id=zone_id,
                         dwell_ms=dwell_ms, sku_zone=sku_zone)

    def billing_join(self, dt, queue_depth=1):
        return self._evt(self.cam_bill, "BILLING_QUEUE_JOIN", dt,
                         zone_id="BILLING", sku_zone="BILLING", queue_depth=queue_depth)

    def billing_abandon(self, dt, dwell_ms=0):
        return self._evt(self.cam_bill, "BILLING_QUEUE_ABANDON", dt,
                         zone_id="BILLING", sku_zone="BILLING", dwell_ms=dwell_ms)


# ── Per-store event generation ────────────────────────────────────────────────

def generate_store_blr_002() -> tuple[list, list]:
    """
    Generate events + POS transactions for STORE_BLR_002.

    Scenario:
      - 18 unique customer visitors (VIS_001–VIS_018)
      -  2 staff members (VIS_S01, VIS_S02)
      -  1 re-entry visitor (VIS_009 exits and comes back)
      -  7 conversions (with matching POS transactions)
      -  3 billing abandonments
      -  Group entry: 3 customers arrive together at T+45min
      -  Queue spike: 4 people in billing at T+90min

    Conversion rate: 7/18 ≈ 38.9%
    """
    SID   = "STORE_BLR_002"
    CE    = "CAM_ENTRY_01"
    CF    = "CAM_FLOOR_01"
    CB    = "CAM_BILL_01"

    ZONES = [
        ("SKINCARE",  "MOISTURISER"),
        ("HAIRCARE",  "SHAMPOO"),
        ("FRAGRANCE", "PERFUME"),
        ("MAKEUP",    "LIPSTICK"),
    ]

    all_events: list  = []
    pos_records: list = []

    def add_session(s: Session):
        all_events.extend(s.events)

    def add_pos(dt: datetime, store_id: str = SID):
        txn_id = f"TXN_{uuid.uuid4().hex[:6].upper()}"
        pos_records.append({
            "store_id":        store_id,
            "transaction_id":  txn_id,
            "timestamp":       fmt(dt),
            "basket_value_inr": round(random.uniform(299, 3500), 2),
        })

    # ── Staff members ─────────────────────────────────────────────────────────
    for idx, offset in enumerate([0.0, 0.2]):
        s = Session(SID, CE, CF, CB, visitor_id=f"VIS_S0{idx+1}", is_staff=True)
        t = ts(offset)
        s.entry(t); t += timedelta(minutes=2)
        for zone_id, sku in ZONES:
            s.zone_enter(t, zone_id, sku); t += timedelta(seconds=45)
            s.zone_exit(t, zone_id, sku, dwell_ms=45000); t += timedelta(seconds=10)
        add_session(s)

    # ── Regular customers — converted ─────────────────────────────────────────
    converted_vids = []
    for i in range(7):
        offset = 0.2 + i * 0.5
        s = Session(SID, CE, CF, CB)
        converted_vids.append(s.visitor_id)
        t = ts(offset)
        s.entry(t); t += timedelta(minutes=3)
        zone_id, sku = random.choice(ZONES[:3])
        s.zone_enter(t, zone_id, sku); t += timedelta(seconds=35)
        s.zone_dwell(t, zone_id, sku); t += timedelta(seconds=30)
        s.zone_exit(t, zone_id, sku, dwell_ms=65000); t += timedelta(seconds=5)
        bill_t = t
        s.billing_join(bill_t, queue_depth=max(1, i % 3 + 1)); t += timedelta(minutes=4)
        s.exit(t)
        add_session(s)
        # POS transaction 3 minutes after billing join (within 5-min window)
        add_pos(bill_t + timedelta(minutes=3))

    # ── Regular customers — zone-only (no billing) ────────────────────────────
    for i in range(5):
        offset = 0.8 + i * 0.6
        s = Session(SID, CE, CF, CB)
        t = ts(offset)
        s.entry(t); t += timedelta(minutes=2)
        zone_id, sku = random.choice(ZONES)
        s.zone_enter(t, zone_id, sku); t += timedelta(seconds=60)
        s.zone_dwell(t, zone_id, sku, dwell_ms=30000); t += timedelta(seconds=30)
        s.zone_exit(t, zone_id, sku, dwell_ms=90000); t += timedelta(minutes=2)
        s.exit(t)
        add_session(s)

    # ── Billing abandoners ────────────────────────────────────────────────────
    for i in range(3):
        offset = 1.5 + i * 0.8
        s = Session(SID, CE, CF, CB)
        t = ts(offset)
        s.entry(t); t += timedelta(minutes=4)
        zone_id, sku = random.choice(ZONES)
        s.zone_enter(t, zone_id, sku); t += timedelta(seconds=45)
        s.zone_exit(t, zone_id, sku, dwell_ms=45000); t += timedelta(seconds=5)
        s.billing_join(t, queue_depth=2); t += timedelta(minutes=6)
        s.billing_abandon(t, dwell_ms=360000)
        s.exit(t + timedelta(minutes=1))
        add_session(s)

    # ── Group entry (3 people arrive together at T+45min) ─────────────────────
    group_t = ts(0.75)
    for i in range(3):
        s = Session(SID, CE, CF, CB)
        t = group_t + timedelta(seconds=i * 2)   # 2s apart → same "group"
        s.entry(t); t += timedelta(minutes=5)
        zone_id, sku = ZONES[i % len(ZONES)]
        s.zone_enter(t, zone_id, sku); t += timedelta(minutes=3)
        s.zone_exit(t, zone_id, sku, dwell_ms=180000); t += timedelta(minutes=1)
        s.exit(t)
        add_session(s)

    # ── Re-entry visitor ──────────────────────────────────────────────────────
    re_vid = vid()
    s1 = Session(SID, CE, CF, CB, visitor_id=re_vid)
    t = ts(2.0)
    s1.entry(t); t += timedelta(minutes=5)
    s1.zone_enter(t, "SKINCARE", "MOISTURISER"); t += timedelta(minutes=2)
    s1.zone_exit(t, "SKINCARE", "MOISTURISER", dwell_ms=120000); t += timedelta(minutes=1)
    s1.exit(t)
    add_session(s1)

    s2 = Session(SID, CE, CF, CB, visitor_id=re_vid)
    t += timedelta(minutes=12)   # comes back 12 minutes later
    s2.reentry(t); t += timedelta(minutes=3)
    s2.zone_enter(t, "HAIRCARE", "SHAMPOO"); t += timedelta(minutes=4)
    s2.billing_join(t, queue_depth=1); t += timedelta(minutes=3)
    s2.exit(t + timedelta(minutes=1))
    add_session(s2)
    add_pos(t)   # re-entry visitor converts

    # ── Low-confidence detection (partial occlusion edge case) ────────────────
    s = Session(SID, CE, CF, CB)
    t = ts(3.5)
    s.entry(t); t += timedelta(minutes=2)
    # Low confidence events — still emitted (scoring criterion)
    all_events.append({
        "event_id": eid(), "store_id": SID, "camera_id": CF,
        "visitor_id": s.visitor_id, "event_type": "ZONE_ENTER",
        "timestamp": fmt(t), "zone_id": "SKINCARE", "dwell_ms": 0,
        "is_staff": False, "confidence": 0.31,
        "metadata": {"queue_depth": None, "sku_zone": "MOISTURISER", "session_seq": 2},
    })
    t += timedelta(minutes=5)
    s._evt(CE, "EXIT", t)
    add_session(s)

    all_events.sort(key=lambda e: e["timestamp"])
    return all_events, pos_records


def generate_store_simple(store_id: str, n_visitors: int = 8,
                           n_converted: int = 2) -> tuple[list, list]:
    """Generate minimal events for secondary stores."""
    layout = json.loads((DATA_DIR / "store_layout.json").read_text())
    store_data = layout.get(store_id, {})
    cameras    = store_data.get("cameras", [])
    zones      = store_data.get("zones", [])

    CE = next((c["camera_id"] for c in cameras if c["type"] == "entry_exit"), "CAM_ENTRY_01")
    CF = next((c["camera_id"] for c in cameras if c["type"] == "main_floor"), "CAM_FLOOR_01")
    CB = next((c["camera_id"] for c in cameras if c["type"] == "billing"),    "CAM_BILL_01")

    product_zones = [(z["zone_id"], z["sku_zone"]) for z in zones if z["zone_id"] != "BILLING"]

    all_events: list  = []
    pos_records: list = []

    for i in range(n_visitors):
        s = Session(store_id, CE, CF, CB)
        t = ts(0.5 + i * 0.4)
        s.entry(t); t += timedelta(minutes=3)
        if product_zones:
            zone_id, sku = random.choice(product_zones)
            s.zone_enter(t, zone_id, sku); t += timedelta(minutes=4)
            s.zone_exit(t, zone_id, sku, dwell_ms=240000)

        if i < n_converted:
            t += timedelta(seconds=30)
            bill_t = t
            s.billing_join(t, queue_depth=1); t += timedelta(minutes=3)
            pos_records.append({
                "store_id":        store_id,
                "transaction_id":  f"TXN_{uuid.uuid4().hex[:6].upper()}",
                "timestamp":       fmt(bill_t + timedelta(minutes=2)),
                "basket_value_inr": round(random.uniform(399, 2500), 2),
            })

        t += timedelta(minutes=1)
        s.exit(t)
        all_events.extend(s.events)

    all_events.sort(key=lambda e: e["timestamp"])
    return all_events, pos_records


# ── Write helpers ─────────────────────────────────────────────────────────────

def write_jsonl(events: list, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    print(f"  Written {len(events):>4} events → {path.relative_to(ROOT)}")


def write_pos_csv(records: list, path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["store_id","transaction_id","timestamp","basket_value_inr"])
        writer.writeheader()
        writer.writerows(records)
    print(f"  Written {len(records):>4} POS rows  → {path.relative_to(ROOT)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║   Store Intelligence — Synthetic Dataset Generator       ║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    print(f"  Generating data for: {NOW.strftime('%Y-%m-%d')} (today)\n")

    all_pos: list = []

    # ── STORE_BLR_002 (primary — most detailed) ────────────────────────────
    print("▸ STORE_BLR_002")
    events_blr, pos_blr = generate_store_blr_002()
    write_jsonl(events_blr, EVENTS_DIR / "STORE_BLR_002.jsonl")
    all_pos.extend(pos_blr)

    # ── STORE_DEL_001 ──────────────────────────────────────────────────────
    print("▸ STORE_DEL_001")
    events_del, pos_del = generate_store_simple("STORE_DEL_001", n_visitors=10, n_converted=3)
    write_jsonl(events_del, EVENTS_DIR / "STORE_DEL_001.jsonl")
    all_pos.extend(pos_del)

    # ── STORE_MUM_001 ──────────────────────────────────────────────────────
    print("▸ STORE_MUM_001")
    events_mum, pos_mum = generate_store_simple("STORE_MUM_001", n_visitors=12, n_converted=5)
    write_jsonl(events_mum, EVENTS_DIR / "STORE_MUM_001.jsonl")
    all_pos.extend(pos_mum)

    # ── pos_transactions.csv (all stores combined) ─────────────────────────
    print("\n▸ POS transactions")
    all_pos.sort(key=lambda r: r["timestamp"])
    write_pos_csv(all_pos, DATA_DIR / "pos_transactions.csv")

    # ── sample_events.jsonl (first 200 from primary store, for schema ref) ─
    print("\n▸ sample_events.jsonl (schema reference)")
    sample = events_blr[:200]
    write_jsonl(sample, DATA_DIR / "sample_events.jsonl")

    # ── Summary ────────────────────────────────────────────────────────────
    total_events = len(events_blr) + len(events_del) + len(events_mum)
    print(f"""
╔══════════════════════════════════════════════════════════╗
║  Dataset generated successfully!                         ║
╠══════════════════════════════════════════════════════════╣
║  Events total   : {total_events:<4}                                  ║
║  POS records    : {len(all_pos):<4}                                  ║
║  Stores         : STORE_BLR_002, STORE_DEL_001,          ║
║                   STORE_MUM_001                           ║
╠══════════════════════════════════════════════════════════╣
║  Next steps:                                             ║
║                                                          ║
║  1. docker compose up --build                            ║
║                                                          ║
║  2. python scripts/ingest_events.py                      ║
║     (ingests all JSONL files into the running API)       ║
║                                                          ║
║  3. curl http://localhost:8000/stores/STORE_BLR_002/     ║
║          metrics | python3 -m json.tool                  ║
║                                                          ║
║  4. open http://localhost:8000/dashboard                  ║
╚══════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
