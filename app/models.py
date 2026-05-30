import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.db import Base


class Event(Base):
    """
    One row per structured behavioural event emitted by the detection pipeline.
    event_id is the idempotency key — duplicate POSTs are silently ignored.
    """

    __tablename__ = "events"

    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(32), nullable=False)
    camera_id = Column(String(32), nullable=False)
    visitor_id = Column(String(32), nullable=False)
    event_type = Column(String(32), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    zone_id = Column(String(64), nullable=True)
    dwell_ms = Column(Integer, nullable=False, server_default="0")
    is_staff = Column(Boolean, nullable=False, server_default="false")
    confidence = Column(Float, nullable=False)
    queue_depth = Column(Integer, nullable=True)
    sku_zone = Column(String(64), nullable=True)
    session_seq = Column(Integer, nullable=False, server_default="1")
    ingested_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        # Covers metrics queries: all events for a store in a time range
        Index("ix_events_store_ts", "store_id", "timestamp"),
        # Covers session reconstruction: all events for a visitor in a store
        Index("ix_events_visitor_store", "visitor_id", "store_id"),
        # Covers anomaly queries: filter by event_type within a store+time range
        Index("ix_events_store_type_ts", "store_id", "event_type", "timestamp"),
        # Covers staff exclusion: fast filter on is_staff before aggregating
        Index("ix_events_store_staff_ts", "store_id", "is_staff", "timestamp"),
    )


class VisitorSession(Base):
    """
    One row per visitor visit session (ENTRY → EXIT window).
    Reconstructed from events during ingest. Re-entries reuse the same session.
    """

    __tablename__ = "sessions"

    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(32), nullable=False)
    visitor_id = Column(String(32), nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    is_staff = Column(Boolean, nullable=False, server_default="false")
    visited_zones = Column(
        ARRAY(String), nullable=False, server_default=text("'{}'::text[]")
    )
    reached_billing = Column(Boolean, nullable=False, server_default="false")
    converted = Column(Boolean, nullable=False, server_default="false")
    session_date = Column(Date, nullable=False)

    __table_args__ = (
        # Prevents double-counting when the same ENTRY event is ingested twice
        UniqueConstraint(
            "visitor_id",
            "store_id",
            "entry_time",
            name="uq_session_visitor_store_entry",
        ),
        # Covers daily metrics queries
        Index("ix_sessions_store_date", "store_id", "session_date"),
    )


class POSTransaction(Base):
    """
    Loaded from pos_transactions.csv at startup.
    Used to correlate billing-zone presence with purchases (5-minute window).
    """

    __tablename__ = "pos_transactions"

    transaction_id = Column(String(128), primary_key=True)
    store_id = Column(String(32), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    basket_value_inr = Column(Numeric(10, 2), nullable=False)

    __table_args__ = (
        # Covers the 5-minute window lookup: store + narrow time range
        Index("ix_pos_store_ts", "store_id", "timestamp"),
    )


class AnomalyBaseline(Base):
    """
    Rolling 7-day per-hour averages used to detect anomalies.
    Updated once daily. Missing row = not enough history to detect yet.
    """

    __tablename__ = "anomaly_baselines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(String(32), nullable=False)
    metric_name = Column(String(64), nullable=False)
    hour_of_day = Column(Integer, nullable=False)  # 0–23
    avg_7d = Column(Float, nullable=False)
    stddev_7d = Column(Float, nullable=False)
    computed_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "metric_name",
            "hour_of_day",
            name="uq_baseline_store_metric_hour",
        ),
    )
