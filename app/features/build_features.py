from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Asset,
    AssetDataCoverage,
    DexSnapshot,
    Feature,
    HLLiquidationCluster,
    MarketSnapshot,
    OrderbookSnapshot,
)
from app.features.percentiles import median_multiple, percentile_rank
from app.features.rolling_windows import pct_change
from app.utils.time import floor_time


@dataclass(frozen=True)
class FeatureValue:
    name: str
    window: str
    value: float | None
    metadata: dict


async def build_latest_features(session: AsyncSession) -> int:
    ts = floor_time(seconds=60)
    asset_ids = [row[0] for row in (await session.execute(select(Asset.id).where(Asset.is_active.is_(True)))).all()]
    written = 0
    for asset_id in asset_ids:
        features = await build_asset_features(session, asset_id, ts)
        for feature in features:
            stmt = (
                insert(Feature)
                .values(
                    ts=ts,
                    asset_id=asset_id,
                    feature_name=feature.name,
                    window=feature.window,
                    value=feature.value,
                    metadata_=feature.metadata,
                )
                .on_conflict_do_update(
                    index_elements=[Feature.ts, Feature.asset_id, Feature.feature_name, Feature.window],
                    set_={"value": feature.value, "metadata": feature.metadata},
                )
            )
            await session.execute(stmt)
            written += 1
    await session.commit()
    return written


async def build_asset_features(session: AsyncSession, asset_id: int, ts) -> list[FeatureValue]:
    market_rows = (
        await session.execute(
            select(MarketSnapshot)
            .where(MarketSnapshot.asset_id == asset_id)
            .where(MarketSnapshot.ts >= ts - timedelta(days=90))
            .order_by(MarketSnapshot.ts)
        )
    ).scalars().all()
    orderbook_rows = (
        await session.execute(
            select(OrderbookSnapshot)
            .where(OrderbookSnapshot.asset_id == asset_id)
            .where(OrderbookSnapshot.ts >= ts - timedelta(days=90))
            .order_by(OrderbookSnapshot.ts)
        )
    ).scalars().all()
    dex_rows = (
        await session.execute(
            select(DexSnapshot)
            .where(DexSnapshot.asset_id == asset_id)
            .where(DexSnapshot.ts >= ts - timedelta(days=90))
            .order_by(DexSnapshot.ts)
        )
    ).scalars().all()
    hl_clusters = (
        await session.execute(
            select(HLLiquidationCluster)
            .where(HLLiquidationCluster.asset_id == asset_id)
            .where(HLLiquidationCluster.ts >= ts - timedelta(hours=4))
            .order_by(HLLiquidationCluster.ts)
        )
    ).scalars().all()
    coverage = (
        await session.execute(select(AssetDataCoverage).where(AssetDataCoverage.asset_id == asset_id))
    ).scalar_one_or_none()

    features: list[FeatureValue] = []
    latest_by_venue = _latest_market_by_venue(market_rows)
    merged_latest = _aggregate_latest_market(latest_by_venue)
    for minutes, window in [(5, "5m"), (15, "15m"), (60, "1h"), (240, "4h")]:
        previous = _aggregate_at_or_before(market_rows, ts - timedelta(minutes=minutes))
        price_change = pct_change(merged_latest.get("price"), previous.get("price"))
        oi_change = pct_change(merged_latest.get("open_interest_usd"), previous.get("open_interest_usd"))
        features.append(FeatureValue("price_change", window, price_change, {}))
        features.append(FeatureValue("oi_change", window, oi_change, {}))

    oi_1h = next((item.value for item in features if item.name == "oi_change" and item.window == "1h"), None)
    oi_history = _window_changes(market_rows, "open_interest_usd", minutes=60)
    features.extend(
        [
            FeatureValue("oi_change_percentile", "90d_1h", percentile_rank(oi_1h, oi_history), {}),
            FeatureValue("oi_change_median_multiple", "90d_1h", median_multiple(oi_1h, oi_history), {}),
        ]
    )

    price_1h = next((item.value for item in features if item.name == "price_change" and item.window == "1h"), None)
    price_history = _window_changes(market_rows, "price", minutes=60)
    features.append(
        FeatureValue("price_change_percentile", "90d_1h", percentile_rank(price_1h, price_history), {})
    )

    funding_values = [row.funding_rate for row in market_rows if row.funding_rate is not None]
    latest_funding = _latest_value(market_rows, "funding_rate")
    features.append(FeatureValue("funding_current", "latest", latest_funding, {}))
    features.append(
        FeatureValue("funding_percentile", "90d", percentile_rank(latest_funding, funding_values), {})
    )

    depth_latest = _latest_depth_total(orderbook_rows)
    depth_history = _depth_totals(orderbook_rows)
    features.append(FeatureValue("depth_100bps_total_usd", "latest", depth_latest, {}))
    features.append(
        FeatureValue("depth_100bps_percentile", "90d", percentile_rank(depth_latest, depth_history), {})
    )
    features.append(
        FeatureValue("depth_100bps_median_multiple", "90d", median_multiple(depth_latest, depth_history), {})
    )
    for minutes, window in [(15, "15m"), (60, "1h")]:
        previous_depth = _depth_at_or_before(orderbook_rows, ts - timedelta(minutes=minutes))
        features.append(FeatureValue("depth_100bps_change", window, pct_change(depth_latest, previous_depth), {}))

    latest_dex = dex_rows[-1] if dex_rows else None
    features.append(
        FeatureValue(
            "dex_liquidity_usd",
            "latest",
            latest_dex.liquidity_usd if latest_dex else None,
            {"dexscreener_url": latest_dex.dexscreener_url if latest_dex else None},
        )
    )
    for minutes, window in [(60, "1h"), (1440, "24h")]:
        previous = next((row for row in reversed(dex_rows) if row.ts <= ts - timedelta(minutes=minutes)), None)
        features.append(
            FeatureValue(
                "dex_liquidity_change",
                window,
                pct_change(latest_dex.liquidity_usd if latest_dex else None, previous.liquidity_usd if previous else None),
                {},
            )
        )

    if coverage:
        features.append(FeatureValue("supported_venue_count", "latest", float(len(set((coverage.spot_venues or []) + (coverage.perp_venues or [])))), {}))
        features.append(FeatureValue("spot_venue_count", "latest", float(len(coverage.spot_venues or [])), {}))
        features.append(FeatureValue("perp_venue_count", "latest", float(len(coverage.perp_venues or [])), {}))

    features.extend(_venue_share_features(latest_by_venue))
    features.extend(_hl_liquidation_features(hl_clusters, merged_latest.get("price"), merged_latest.get("volume_24h_usd")))
    return features


def _latest_market_by_venue(rows: list[MarketSnapshot]) -> dict[tuple[str, str], MarketSnapshot]:
    latest: dict[tuple[str, str], MarketSnapshot] = {}
    for row in rows:
        latest[(row.venue, row.market_type)] = row
    return latest


def _aggregate_latest_market(rows: dict[tuple[str, str], MarketSnapshot]) -> dict[str, float | None]:
    latest_price = next((row.price for row in reversed(list(rows.values())) if row.price is not None), None)
    return {
        "price": latest_price,
        "open_interest_usd": sum(row.open_interest_usd or 0 for row in rows.values()) or None,
        "volume_24h_usd": sum(row.volume_24h_usd or 0 for row in rows.values()) or None,
    }


def _aggregate_at_or_before(rows: list[MarketSnapshot], at_ts) -> dict[str, float | None]:
    by_venue: dict[tuple[str, str], MarketSnapshot] = {}
    for row in rows:
        if row.ts <= at_ts:
            by_venue[(row.venue, row.market_type)] = row
    return _aggregate_latest_market(by_venue)


def _latest_value(rows: list[MarketSnapshot], attr: str) -> float | None:
    for row in reversed(rows):
        value = getattr(row, attr)
        if value is not None:
            return value
    return None


def _window_changes(rows: list[MarketSnapshot], attr: str, minutes: int) -> list[float]:
    grouped: dict[tuple[str, str], list[MarketSnapshot]] = defaultdict(list)
    for row in rows:
        grouped[(row.venue, row.market_type)].append(row)
    changes: list[float] = []
    for series in grouped.values():
        for idx, row in enumerate(series):
            previous_ts = row.ts - timedelta(minutes=minutes)
            previous = next((item for item in reversed(series[:idx]) if item.ts <= previous_ts), None)
            change = pct_change(getattr(row, attr), getattr(previous, attr) if previous else None)
            if change is not None:
                changes.append(change)
    return changes


def _depth_total(row: OrderbookSnapshot) -> float:
    return (row.bid_depth_100bps_usd or 0) + (row.ask_depth_100bps_usd or 0)


def _latest_depth_total(rows: list[OrderbookSnapshot]) -> float | None:
    if not rows:
        return None
    return sum(_depth_total(row) for row in rows if row.ts == rows[-1].ts) or None


def _depth_totals(rows: list[OrderbookSnapshot]) -> list[float]:
    by_ts: dict = defaultdict(float)
    for row in rows:
        by_ts[row.ts] += _depth_total(row)
    return list(by_ts.values())


def _depth_at_or_before(rows: list[OrderbookSnapshot], at_ts) -> float | None:
    eligible = [row for row in rows if row.ts <= at_ts]
    if not eligible:
        return None
    latest_ts = eligible[-1].ts
    return sum(_depth_total(row) for row in eligible if row.ts == latest_ts) or None


def _venue_share_features(latest_by_venue: dict[tuple[str, str], MarketSnapshot]) -> list[FeatureValue]:
    features: list[FeatureValue] = []
    total_oi = sum(row.open_interest_usd or 0 for row in latest_by_venue.values())
    total_volume = sum(row.volume_24h_usd or 0 for row in latest_by_venue.values())
    for (venue, market_type), row in latest_by_venue.items():
        if total_oi and row.open_interest_usd:
            features.append(FeatureValue("venue_oi_share", "latest", row.open_interest_usd / total_oi, {"venue": venue, "market_type": market_type}))
        if total_volume and row.volume_24h_usd:
            features.append(FeatureValue("venue_volume_share", "latest", row.volume_24h_usd / total_volume, {"venue": venue, "market_type": market_type}))
        if venue == "upbit" and total_volume and row.volume_24h_usd:
            features.append(FeatureValue("upbit_volume_share", "latest", row.volume_24h_usd / total_volume, {"venue": venue}))
    return features


def _hl_liquidation_features(
    clusters: list[HLLiquidationCluster], price: float | None, volume_24h: float | None
) -> list[FeatureValue]:
    if not clusters or not price:
        return []
    latest_ts = clusters[-1].ts
    latest = [row for row in clusters if row.ts == latest_ts]
    nearest = min(latest, key=lambda row: abs((row.price_bucket - price) / price))
    distance = ((nearest.price_bucket - price) / price) * 100.0
    return [
        FeatureValue("hl_liq_cluster_distance_pct", "nearest", distance, {"side": nearest.side, "market": nearest.market}),
        FeatureValue("hl_liq_cluster_size_usd", "nearest", nearest.cluster_notional_usd, {"side": nearest.side, "market": nearest.market}),
        FeatureValue(
            "hl_liq_cluster_size_vs_volume",
            "nearest",
            nearest.cluster_notional_usd / volume_24h if volume_24h else None,
            {"side": nearest.side, "market": nearest.market},
        ),
    ]
