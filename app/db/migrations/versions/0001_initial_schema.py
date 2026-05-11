"""initial schema

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config.exclusions import DEFAULT_EXCLUDED_ASSETS
from app.db.models import Base

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    initial_tables = [
        table for name, table in Base.metadata.tables.items() if name != "hourly_changes"
    ]
    Base.metadata.create_all(bind=bind, tables=initial_tables)

    for symbol in DEFAULT_EXCLUDED_ASSETS:
        reason = "Seeded major/stable exclusion"
        op.execute(
            "INSERT INTO excluded_assets(symbol, reason) VALUES "
            f"('{symbol}', '{reason}') ON CONFLICT (symbol) DO NOTHING"
        )

    hypertables = [
        "market_snapshots",
        "orderbook_snapshots",
        "dex_snapshots",
        "hl_liquidation_clusters",
        "features",
    ]
    for table in hypertables:
        op.execute(
            f"SELECT create_hypertable('{table}', 'ts', if_not_exists => TRUE, migrate_data => TRUE)"
        )

    op.execute("CREATE INDEX IF NOT EXISTS ix_assets_symbol ON assets(symbol)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_venue_symbols_asset ON venue_symbols(asset_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_market_snapshots_lookup ON market_snapshots(asset_id, venue, market_type, ts DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_orderbook_snapshots_lookup ON orderbook_snapshots(asset_id, venue, market_type, ts DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dex_snapshots_lookup ON dex_snapshots(asset_id, ts DESC)")
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_features_latest ON features(asset_id, feature_name, "window", ts DESC)'
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_alerts_latest ON alerts(ts DESC, telegram_sent, severity)")


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
