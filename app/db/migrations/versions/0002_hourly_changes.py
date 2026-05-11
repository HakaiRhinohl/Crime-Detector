"""add hourly changes

Revision ID: 0002_hourly_changes
Revises: 0001_initial_schema
Create Date: 2026-05-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_hourly_changes"
down_revision: str | None = "0001_initial_schema"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hourly_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("pct_change", sa.Float(), nullable=True),
        sa.Column("hour_block", sa.Integer(), nullable=False),
        sa.Column("day_type", sa.Text(), nullable=False),
        sa.Column("btc_regime", sa.Text(), nullable=False),
        sa.UniqueConstraint("asset_id", "ts", "metric", name="uq_hourly_change"),
    )
    op.create_index("ix_hourly_changes_lookup", "hourly_changes", ["asset_id", "metric", "ts"])
    op.create_index(
        "ix_hourly_changes_segmented",
        "hourly_changes",
        ["asset_id", "metric", "hour_block", "day_type", "btc_regime"],
    )


def downgrade() -> None:
    op.drop_index("ix_hourly_changes_segmented", table_name="hourly_changes")
    op.drop_index("ix_hourly_changes_lookup", table_name="hourly_changes")
    op.drop_table("hourly_changes")
