"""Initial schema — all four tables

Revision ID: 001
Revises:
Create Date: 2026-03-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # events — core table; one row per behavioural event from the pipeline
    # ------------------------------------------------------------------
    op.create_table(
        "events",
        sa.Column(
            "event_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("camera_id", sa.String(32), nullable=False),
        sa.Column("visitor_id", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("zone_id", sa.String(64), nullable=True),
        sa.Column("dwell_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_staff", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("queue_depth", sa.Integer(), nullable=True),
        sa.Column("sku_zone", sa.String(64), nullable=True),
        sa.Column("session_seq", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_events_store_ts", "events", ["store_id", "timestamp"])
    op.create_index("ix_events_visitor_store", "events", ["visitor_id", "store_id"])
    op.create_index(
        "ix_events_store_type_ts", "events", ["store_id", "event_type", "timestamp"]
    )
    op.create_index(
        "ix_events_store_staff_ts", "events", ["store_id", "is_staff", "timestamp"]
    )

    # ------------------------------------------------------------------
    # sessions — one row per visitor visit; reconstructed from events
    # ------------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column(
            "session_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("visitor_id", sa.String(32), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_staff", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "visited_zones",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("reached_billing", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("converted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.UniqueConstraint(
            "visitor_id",
            "store_id",
            "entry_time",
            name="uq_session_visitor_store_entry",
        ),
    )
    op.create_index("ix_sessions_store_date", "sessions", ["store_id", "session_date"])

    # ------------------------------------------------------------------
    # pos_transactions — loaded from pos_transactions.csv at API startup
    # ------------------------------------------------------------------
    op.create_table(
        "pos_transactions",
        sa.Column("transaction_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basket_value_inr", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("ix_pos_store_ts", "pos_transactions", ["store_id", "timestamp"])

    # ------------------------------------------------------------------
    # anomaly_baselines — rolling 7-day hourly averages for anomaly detection
    # ------------------------------------------------------------------
    op.create_table(
        "anomaly_baselines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("hour_of_day", sa.Integer(), nullable=False),
        sa.Column("avg_7d", sa.Float(), nullable=False),
        sa.Column("stddev_7d", sa.Float(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "store_id",
            "metric_name",
            "hour_of_day",
            name="uq_baseline_store_metric_hour",
        ),
    )


def downgrade() -> None:
    op.drop_table("anomaly_baselines")
    op.drop_index("ix_pos_store_ts", table_name="pos_transactions")
    op.drop_table("pos_transactions")
    op.drop_index("ix_sessions_store_date", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_events_store_staff_ts", table_name="events")
    op.drop_index("ix_events_store_type_ts", table_name="events")
    op.drop_index("ix_events_visitor_store", table_name="events")
    op.drop_index("ix_events_store_ts", table_name="events")
    op.drop_table("events")
