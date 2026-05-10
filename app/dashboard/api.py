from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Alert,
    Asset,
    AssetDataCoverage,
    DexSnapshot,
    Feature,
    HLLiquidationCluster,
    MarketSnapshot,
    OrderbookSnapshot,
)
from app.db.session import get_db

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/alerts")
async def alerts(session: SessionDep, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(select(Alert, Asset).join(Asset, Asset.id == Alert.asset_id).order_by(Alert.ts.desc()).limit(limit))
    ).all()
    return [
        {
            "id": alert.id,
            "ts": alert.ts,
            "symbol": asset.symbol,
            "detector": alert.detector,
            "severity": alert.severity,
            "title": alert.title,
            "message": alert.message,
            "telegram_sent": alert.telegram_sent,
            "venues": alert.venues,
            "metrics": alert.metrics,
            "dexscreener_url": alert.dexscreener_url,
        }
        for alert, asset in rows
    ]


@router.get("/candidates")
async def candidates(session: SessionDep, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(
            select(Alert, Asset)
            .join(Asset, Asset.id == Alert.asset_id)
            .where(Alert.telegram_sent.is_(False))
            .order_by(Alert.ts.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": alert.id,
            "ts": alert.ts,
            "symbol": asset.symbol,
            "detector": alert.detector,
            "severity": alert.severity,
            "message": alert.message,
            "venues": alert.venues,
            "metrics": alert.metrics,
        }
        for alert, asset in rows
    ]


@router.get("/asset/{symbol}")
async def asset_detail(symbol: str, session: SessionDep) -> dict:
    asset = (
        await session.execute(select(Asset).where(Asset.symbol == symbol.upper()))
    ).scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    coverage = (
        await session.execute(select(AssetDataCoverage).where(AssetDataCoverage.asset_id == asset.id))
    ).scalar_one_or_none()
    market = (
        await session.execute(
            select(MarketSnapshot)
            .where(MarketSnapshot.asset_id == asset.id)
            .order_by(MarketSnapshot.ts.desc())
            .limit(500)
        )
    ).scalars().all()
    orderbooks = (
        await session.execute(
            select(OrderbookSnapshot)
            .where(OrderbookSnapshot.asset_id == asset.id)
            .order_by(OrderbookSnapshot.ts.desc())
            .limit(500)
        )
    ).scalars().all()
    dex = (
        await session.execute(
            select(DexSnapshot).where(DexSnapshot.asset_id == asset.id).order_by(DexSnapshot.ts.desc()).limit(100)
        )
    ).scalars().all()
    clusters = (
        await session.execute(
            select(HLLiquidationCluster)
            .where(HLLiquidationCluster.asset_id == asset.id)
            .order_by(HLLiquidationCluster.ts.desc())
            .limit(100)
        )
    ).scalars().all()
    alert_rows = (
        await session.execute(
            select(Alert).where(Alert.asset_id == asset.id).order_by(Alert.ts.desc()).limit(100)
        )
    ).scalars().all()
    feature_rows = (
        await session.execute(
            select(Feature).where(Feature.asset_id == asset.id).order_by(Feature.ts.desc()).limit(200)
        )
    ).scalars().all()

    return {
        "asset": {"id": asset.id, "symbol": asset.symbol, "market_cap": asset.market_cap, "fdv": asset.fdv},
        "coverage": {
            "spot_venues": coverage.spot_venues if coverage else [],
            "perp_venues": coverage.perp_venues if coverage else [],
            "dex_chains": coverage.dex_chains if coverage else [],
        },
        "market": [_market_row(row) for row in reversed(market)],
        "orderbooks": [_orderbook_row(row) for row in reversed(orderbooks)],
        "dex": [_dex_row(row) for row in reversed(dex)],
        "hl_liquidation_clusters": [_cluster_row(row) for row in reversed(clusters)],
        "alerts": [_alert_row(row) for row in alert_rows],
        "features": [
            {"ts": row.ts, "name": row.feature_name, "window": row.window, "value": row.value, "metadata": row.metadata_}
            for row in feature_rows
        ],
    }


def _market_row(row: MarketSnapshot) -> dict:
    return {
        "ts": row.ts,
        "venue": row.venue,
        "market_type": row.market_type,
        "symbol": row.symbol,
        "price": row.price,
        "volume_24h_usd": row.volume_24h_usd,
        "open_interest_usd": row.open_interest_usd,
        "funding_rate": row.funding_rate,
    }


def _orderbook_row(row: OrderbookSnapshot) -> dict:
    return {
        "ts": row.ts,
        "venue": row.venue,
        "market_type": row.market_type,
        "mid_price": row.mid_price,
        "spread_bps": row.spread_bps,
        "depth_100bps_usd": (row.bid_depth_100bps_usd or 0) + (row.ask_depth_100bps_usd or 0),
        "imbalance_100bps": row.imbalance_100bps,
    }


def _dex_row(row: DexSnapshot) -> dict:
    return {
        "ts": row.ts,
        "chain": row.chain,
        "dex_id": row.dex_id,
        "dexscreener_url": row.dexscreener_url,
        "liquidity_usd": row.liquidity_usd,
        "volume_1h_usd": row.volume_1h_usd,
    }


def _cluster_row(row: HLLiquidationCluster) -> dict:
    return {
        "ts": row.ts,
        "market": row.market,
        "side": row.side,
        "price_bucket": row.price_bucket,
        "cluster_notional_usd": row.cluster_notional_usd,
        "positions_count": row.positions_count,
    }


def _alert_row(row: Alert) -> dict:
    return {
        "ts": row.ts,
        "detector": row.detector,
        "severity": row.severity,
        "title": row.title,
        "message": row.message,
        "telegram_sent": row.telegram_sent,
    }
