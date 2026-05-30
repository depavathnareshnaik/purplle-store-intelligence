"""Widen transaction_id to VARCHAR(128) for real Purplle POS data

Revision ID: 002
Revises: 001
Create Date: 2026-05-30 00:00:00.000000
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "pos_transactions", "transaction_id",
        existing_type=sa.String(32),
        type_=sa.String(128),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "pos_transactions", "transaction_id",
        existing_type=sa.String(128),
        type_=sa.String(32),
        existing_nullable=False,
    )
