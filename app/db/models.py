from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSONB}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("symbol", name="uq_assets_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    coingecko_id: Mapped[str | None] = mapped_column(Text)
    cmc_id: Mapped[str | None] = mapped_column(Text)
    circulating_supply: Mapped[float | None] = mapped_column(Float)
    fdv: Mapped[float | None] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ExcludedAsset(Base):
    __tablename__ = "excluded_assets"

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VenueSymbol(Base, TimestampMixin):
    __tablename__ = "venue_symbols"
    __table_args__ = (UniqueConstraint("venue", "market_type", "symbol", name="uq_venue_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    venue: Mapped[str] = mapped_column(Text, nullable=False)
    market_type: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    quote_asset: Mapped[str | None] = mapped_column(Text)
    base_asset: Mapped[str | None] = mapped_column(Text)
    contract_multiplier: Mapped[float] = mapped_column(Numeric, default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default="{}")


class SymbolOverride(Base):
    __tablename__ = "symbol_overrides"

    venue: Mapped[str] = mapped_column(Text, primary_key=True)
    raw_symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    canonical_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    contract_multiplier: Mapped[float] = mapped_column(Numeric, default=1, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text)


class AssetDataCoverage(Base):
    __tablename__ = "asset_data_coverage"

    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    has_spot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    has_perp: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    has_dex: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    has_orderbook: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    has_hl_liquidations: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    spot_venues: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    perp_venues: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    dex_chains: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssetContract(Base, TimestampMixin):
    __tablename__ = "asset_contracts"
    __table_args__ = (UniqueConstraint("chain", "token_address", name="uq_asset_contract_chain_address"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    chain: Mapped[str] = mapped_column(Text, nullable=False)
    token_address: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default="{}")


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    venue: Mapped[str] = mapped_column(Text, primary_key=True)
    market_type: Mapped[str] = mapped_column(Text, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    price: Mapped[float | None] = mapped_column(Float)
    volume_24h_usd: Mapped[float | None] = mapped_column(Float)
    volume_1m_usd: Mapped[float | None] = mapped_column(Float)
    volume_5m_usd: Mapped[float | None] = mapped_column(Float)
    open_interest_usd: Mapped[float | None] = mapped_column(Float)
    funding_rate: Mapped[float | None] = mapped_column(Float)
    mark_price: Mapped[float | None] = mapped_column(Float)
    index_price: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[dict | None] = mapped_column(JSONB)


class OrderbookSnapshot(Base):
    __tablename__ = "orderbook_snapshots"

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    venue: Mapped[str] = mapped_column(Text, primary_key=True)
    market_type: Mapped[str] = mapped_column(Text, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    mid_price: Mapped[float | None] = mapped_column(Float)
    spread_bps: Mapped[float | None] = mapped_column(Float)
    bid_depth_50bps_usd: Mapped[float | None] = mapped_column(Float)
    ask_depth_50bps_usd: Mapped[float | None] = mapped_column(Float)
    bid_depth_100bps_usd: Mapped[float | None] = mapped_column(Float)
    ask_depth_100bps_usd: Mapped[float | None] = mapped_column(Float)
    bid_depth_200bps_usd: Mapped[float | None] = mapped_column(Float)
    ask_depth_200bps_usd: Mapped[float | None] = mapped_column(Float)
    imbalance_100bps: Mapped[float | None] = mapped_column(Float)
    raw_top_levels: Mapped[dict | None] = mapped_column(JSONB)


class DexSnapshot(Base):
    __tablename__ = "dex_snapshots"

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    chain: Mapped[str] = mapped_column(Text, primary_key=True)
    pair_address: Mapped[str] = mapped_column(Text, primary_key=True)
    dex_id: Mapped[str | None] = mapped_column(Text)
    dexscreener_url: Mapped[str | None] = mapped_column(Text)
    price_usd: Mapped[float | None] = mapped_column(Float)
    liquidity_usd: Mapped[float | None] = mapped_column(Float)
    volume_5m_usd: Mapped[float | None] = mapped_column(Float)
    volume_1h_usd: Mapped[float | None] = mapped_column(Float)
    volume_6h_usd: Mapped[float | None] = mapped_column(Float)
    volume_24h_usd: Mapped[float | None] = mapped_column(Float)
    buys_1h: Mapped[int | None] = mapped_column(Integer)
    sells_1h: Mapped[int | None] = mapped_column(Integer)
    fdv: Mapped[float | None] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[dict | None] = mapped_column(JSONB)


class HLLiquidationCluster(Base):
    __tablename__ = "hl_liquidation_clusters"

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    market: Mapped[str] = mapped_column(Text, primary_key=True)
    side: Mapped[str] = mapped_column(Text, primary_key=True)
    price_bucket: Mapped[float] = mapped_column(Float, primary_key=True)
    cluster_notional_usd: Mapped[float] = mapped_column(Float, nullable=False)
    distance_to_spot_pct: Mapped[float | None] = mapped_column(Float)
    positions_count: Mapped[int | None] = mapped_column(Integer)
    cluster_age_minutes: Mapped[int | None] = mapped_column(Integer)
    raw: Mapped[dict | None] = mapped_column(JSONB)


class Feature(Base):
    __tablename__ = "features"

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    feature_name: Mapped[str] = mapped_column(Text, primary_key=True)
    window: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[float | None] = mapped_column(Float)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default="{}")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    detector: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    interpretation: Mapped[str | None] = mapped_column(Text)
    venues: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    dexscreener_url: Mapped[str | None] = mapped_column(Text)
    telegram_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlertState(Base):
    __tablename__ = "alert_state"

    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    detector: Mapped[str] = mapped_column(Text, primary_key=True)
    event_key: Mapped[str] = mapped_column(Text, primary_key=True)
    last_alert_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_severity: Mapped[str | None] = mapped_column(Text)
    last_metric_value: Mapped[float | None] = mapped_column(Float)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default="{}")

