from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

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
from app.features.ewma import ewma_zscore
from app.features.hourly_changes import (
    MIN_SEGMENT_OBSERVATIONS,
    hourly_change_history,
    hourly_change_rows_for_asset,
    segmented_hourly_change_history,
    upsert_hourly_change_rows,
    window_changes_with_timestamps,
)
from app.features.percentiles import directional_median_multiple, median_multiple, percentile_rank
from app.features.rolling_windows import pct_change, safe_ratio
from app.features.segmentation import BTCRegime, compute_btc_regime, get_segment, serialize_segment
from app.utils.time import floor_time

SEGMENTED_LOOKBACK_DAYS = 60  # TUNABLE: shorter history keeps segmented baselines fresher
UNSEGMENTED_LOOKBACK_DAYS = 90  # TUNABLE: backward-compatible fallback history


@dataclass(frozen=True)
class FeatureValue:
    name: str
    window: str
    value: float | None
    metadata: dict


async def build_latest_features(session: AsyncSession) -> int:
    ts = floor_time(seconds=60)
    btc_regime = await compute_btc_regime(session, ts)
    asset_ids = [row[0] for row in (await session.execute(select(Asset.id).where(Asset.is_active.is_(True)))).all()]
    hourly_rows: list[dict] = []
    feature_rows: dict[tuple[datetime, int, str, str], dict] = {}
    for asset_id in asset_ids:
        features = await build_asset_features(session, asset_id, ts, btc_regime, hourly_rows=hourly_rows)
        for feature in features:
            key = (ts, asset_id, feature.name, feature.window)
            feature_rows[key] = dict(
                ts=ts,
                asset_id=asset_id,
                feature_name=feature.name,
                window=feature.window,
                value=feature.value,
                metadata_=feature.metadata,
            )
    await upsert_hourly_change_rows(session, hourly_rows)
    await _upsert_feature_rows(session, list(feature_rows.values()))
    await session.commit()
    return len(feature_rows)


async def _upsert_feature_rows(session: AsyncSession, rows: list[dict]) -> int:
    if not rows:
        return 0
    for chunk_start in range(0, len(rows), 3000):
        chunk = rows[chunk_start : chunk_start + 3000]
        stmt = insert(Feature).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Feature.ts, Feature.asset_id, Feature.feature_name, Feature.window],
            set_={"value": stmt.excluded.value, "metadata": stmt.excluded["metadata"]},
        )
        await session.execute(stmt)
    return len(rows)


async def build_asset_features(
    session: AsyncSession,
    asset_id: int,
    ts: datetime,
    btc_regime: BTCRegime,
    hourly_rows: list[dict] | None = None,
) -> list[FeatureValue]:
    start_ts = ts - timedelta(days=UNSEGMENTED_LOOKBACK_DAYS)
    market_rows = (
        await session.execute(
            select(MarketSnapshot)
            .where(MarketSnapshot.asset_id == asset_id)
            .where(MarketSnapshot.ts >= start_ts)
            .order_by(MarketSnapshot.ts)
        )
    ).scalars().all()
    orderbook_rows = (
        await session.execute(
            select(OrderbookSnapshot)
            .where(OrderbookSnapshot.asset_id == asset_id)
            .where(OrderbookSnapshot.ts >= start_ts)
            .order_by(OrderbookSnapshot.ts)
        )
    ).scalars().all()
    dex_rows = (
        await session.execute(
            select(DexSnapshot)
            .where(DexSnapshot.asset_id == asset_id)
            .where(DexSnapshot.ts >= start_ts)
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

    current_segment = get_segment(ts, btc_regime.bucket)
    if market_rows:
        rows = hourly_change_rows_for_asset(asset_id, ts, market_rows, btc_regime.bucket)
        if hourly_rows is None:
            await upsert_hourly_change_rows(session, rows)
        else:
            hourly_rows.extend(rows)

    features: list[FeatureValue] = [
        FeatureValue(
            "btc_regime_return_7d",
            "latest",
            btc_regime.return_7d,
            {"bucket": btc_regime.bucket},
        )
    ]
    latest_by_venue = _latest_market_by_venue(market_rows)
    merged_latest = _aggregate_latest_market(latest_by_venue)
    latest_price = merged_latest.get("price")
    latest_oi = merged_latest.get("open_interest_usd")
    latest_volume = merged_latest.get("volume_24h_usd")
    spot_volume = merged_latest.get("spot_volume_usd")
    perp_volume = merged_latest.get("perp_volume_usd")

    features.extend(
        [
            FeatureValue("spot_volume_usd", "latest", spot_volume, {}),
            FeatureValue("perp_volume_usd", "latest", perp_volume, {}),
            FeatureValue("perp_spot_volume_ratio", "latest", safe_ratio(perp_volume, spot_volume), {}),
            FeatureValue("oi_volume_ratio", "latest", safe_ratio(latest_oi, latest_volume), {}),
        ]
    )

    for minutes, window in [(5, "5m"), (15, "15m"), (60, "1h"), (240, "4h")]:
        previous = _aggregate_at_or_before(market_rows, ts - timedelta(minutes=minutes))
        features.append(FeatureValue("price_change", window, pct_change(latest_price, previous.get("price")), {}))
        features.append(FeatureValue("oi_change", window, pct_change(latest_oi, previous.get("open_interest_usd")), {}))
        features.append(
            FeatureValue("volume_change", window, pct_change(latest_volume, previous.get("volume_24h_usd")), {})
        )

    oi_1h = _feature_value(features, "oi_change", "1h")
    oi_history = await _metric_change_history(session, asset_id, "open_interest_usd", ts, market_rows)
    segmented_oi_history, oi_segment = await _segmented_metric_change_history(
        session, asset_id, "open_interest_usd", ts, current_segment, oi_history
    )
    features.extend(
        [
            FeatureValue(
                "oi_change_percentile",
                "seg_60d_1h",
                _percentile_rank(oi_1h, segmented_oi_history),
                {"segment": oi_segment},
            ),
            FeatureValue("oi_change_percentile", "90d_1h", _percentile_rank(oi_1h, oi_history), {}),
            FeatureValue("oi_change_median_multiple", "90d_1h", median_multiple(oi_1h, oi_history), {}),
            FeatureValue(
                "oi_change_directional_median_multiple",
                "90d_1h",
                directional_median_multiple(oi_1h, oi_history),
                {},
            ),
            FeatureValue("oi_change_zscore", "ewma_1h", ewma_zscore(oi_1h, oi_history), {}),
        ]
    )

    price_1h = _feature_value(features, "price_change", "1h")
    price_history = await _metric_change_history(session, asset_id, "price", ts, market_rows)
    segmented_price_history, price_segment = await _segmented_metric_change_history(
        session, asset_id, "price", ts, current_segment, price_history
    )
    features.extend(
        [
            FeatureValue(
                "price_change_percentile",
                "seg_60d_1h",
                _percentile_rank(price_1h, segmented_price_history),
                {"segment": price_segment},
            ),
            FeatureValue("price_change_percentile", "90d_1h", _percentile_rank(price_1h, price_history), {}),
            FeatureValue(
                "price_change_directional_median_multiple",
                "90d_1h",
                directional_median_multiple(price_1h, price_history),
                {},
            ),
            FeatureValue("price_change_zscore", "ewma_1h", ewma_zscore(price_1h, price_history), {}),
        ]
    )

    volume_1h = _feature_value(features, "volume_change", "1h")
    volume_history = await _metric_change_history(session, asset_id, "volume_24h_usd", ts, market_rows)
    segmented_volume_history, volume_segment = await _segmented_metric_change_history(
        session, asset_id, "volume_24h_usd", ts, current_segment, volume_history
    )
    features.extend(
        [
            FeatureValue(
                "volume_change_percentile",
                "seg_60d_1h",
                _percentile_rank(volume_1h, segmented_volume_history),
                {"segment": volume_segment},
            ),
            FeatureValue("volume_change_percentile", "90d_1h", _percentile_rank(volume_1h, volume_history), {}),
            FeatureValue("volume_change_zscore", "ewma_1h", ewma_zscore(volume_1h, volume_history), {}),
        ]
    )

    ratio_history = _oi_volume_ratio_history(market_rows)
    ratio_points = _oi_volume_ratio_points(market_rows)
    segmented_ratio_history, ratio_segment = _segmented_point_history(
        ratio_points, current_segment, ts - timedelta(days=SEGMENTED_LOOKBACK_DAYS)
    )
    features.extend(
        [
            FeatureValue(
                "oi_volume_ratio_percentile",
                "seg_60d",
                _percentile_rank(safe_ratio(latest_oi, latest_volume), segmented_ratio_history or ratio_history),
                {"segment": ratio_segment},
            ),
            FeatureValue(
                "oi_volume_ratio_percentile",
                "90d",
                _percentile_rank(safe_ratio(latest_oi, latest_volume), ratio_history),
                {},
            ),
        ]
    )

    funding_values = [row.funding_rate for row in market_rows if row.funding_rate is not None]
    latest_funding = _latest_value(market_rows, "funding_rate")
    features.append(FeatureValue("funding_current", "latest", latest_funding, {}))
    features.append(
        FeatureValue("funding_percentile", "90d", _percentile_rank(latest_funding, funding_values), {})
    )
    features.append(
        FeatureValue(
            "funding_oi_divergent",
            "latest",
            _funding_oi_divergent(latest_funding, oi_1h),
            {"funding_rate": latest_funding, "oi_change_1h": oi_1h},
        )
    )

    depth_latest = _latest_depth_total(orderbook_rows)
    depth_history = _depth_totals(orderbook_rows)
    depth_points = _depth_total_points(orderbook_rows)
    segmented_depth_history, depth_segment = _segmented_point_history(
        depth_points, current_segment, ts - timedelta(days=SEGMENTED_LOOKBACK_DAYS)
    )
    depth_imbalance = _latest_weighted_imbalance(orderbook_rows)
    imbalance_points = _imbalance_points(orderbook_rows)
    imbalance_history = [value for _, value in imbalance_points]
    segmented_imbalance_history, imbalance_segment = _segmented_point_history(
        imbalance_points, current_segment, ts - timedelta(days=SEGMENTED_LOOKBACK_DAYS)
    )
    features.extend(
        [
            FeatureValue("depth_100bps_total_usd", "latest", depth_latest, {}),
            FeatureValue(
                "depth_100bps_percentile",
                "seg_60d",
                _percentile_rank(depth_latest, segmented_depth_history or depth_history),
                {"segment": depth_segment},
            ),
            FeatureValue("depth_100bps_percentile", "90d", _percentile_rank(depth_latest, depth_history), {}),
            FeatureValue("depth_100bps_median_multiple", "90d", median_multiple(depth_latest, depth_history), {}),
            FeatureValue("depth_imbalance_100bps", "latest", depth_imbalance, {}),
            FeatureValue(
                "depth_imbalance_percentile",
                "seg_60d",
                _percentile_rank(depth_imbalance, segmented_imbalance_history or imbalance_history),
                {"segment": imbalance_segment},
            ),
            FeatureValue(
                "depth_imbalance_percentile",
                "90d",
                _percentile_rank(depth_imbalance, imbalance_history),
                {},
            ),
        ]
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
    features.append(
        FeatureValue(
            "dex_buy_sell_ratio",
            "latest",
            _dex_buy_sell_ratio(latest_dex),
            {
                "buys_1h": latest_dex.buys_1h if latest_dex else None,
                "sells_1h": latest_dex.sells_1h if latest_dex else None,
            },
        )
    )
    for minutes, window in [(60, "1h"), (1440, "24h")]:
        previous = next((row for row in reversed(dex_rows) if row.ts <= ts - timedelta(minutes=minutes)), None)
        features.append(
            FeatureValue(
                "dex_liquidity_change",
                window,
                pct_change(
                    latest_dex.liquidity_usd if latest_dex else None,
                    previous.liquidity_usd if previous else None,
                ),
                {},
            )
        )

    if coverage:
        venues = set((coverage.spot_venues or []) + (coverage.perp_venues or []))
        features.append(FeatureValue("supported_venue_count", "latest", float(len(venues)), {}))
        features.append(FeatureValue("spot_venue_count", "latest", float(len(coverage.spot_venues or [])), {}))
        features.append(FeatureValue("perp_venue_count", "latest", float(len(coverage.perp_venues or [])), {}))

    features.extend(_venue_share_features(latest_by_venue))
    features.extend(_hl_liquidation_features(hl_clusters, latest_price, latest_volume))
    return features


async def _metric_change_history(
    session: AsyncSession,
    asset_id: int,
    metric: str,
    ts: datetime,
    market_rows: list[MarketSnapshot],
) -> list[float]:
    history = await hourly_change_history(
        session,
        asset_id,
        metric,
        ts,
        days=UNSEGMENTED_LOOKBACK_DAYS,
    )
    if len(history) >= MIN_SEGMENT_OBSERVATIONS:
        return history
    return _window_changes(market_rows, metric, minutes=60)


async def _segmented_metric_change_history(
    session: AsyncSession,
    asset_id: int,
    metric: str,
    ts: datetime,
    current_segment: tuple[int, str, str],
    fallback_history: list[float],
) -> tuple[list[float], str]:
    history, segment = await segmented_hourly_change_history(
        session,
        asset_id,
        metric,
        ts,
        current_segment,
        days=SEGMENTED_LOOKBACK_DAYS,
    )
    if history:
        return history, segment
    return fallback_history, "unsegmented_fallback"


def _feature_value(features: list[FeatureValue], name: str, window: str) -> float | None:
    return next((item.value for item in features if item.name == name and item.window == window), None)


def _percentile_rank(value: float | None, history: list[float]) -> float | None:
    clean = [item for item in history if item is not None]
    if len(clean) < MIN_SEGMENT_OBSERVATIONS:
        return None
    return percentile_rank(value, clean)


def _latest_market_by_venue(rows: list[MarketSnapshot]) -> dict[tuple[str, str], MarketSnapshot]:
    latest: dict[tuple[str, str], MarketSnapshot] = {}
    for row in rows:
        latest[(row.venue, row.market_type)] = row
    return latest


def _aggregate_latest_market(rows: dict[tuple[str, str], MarketSnapshot]) -> dict[str, float | None]:
    latest_price = next((row.price for row in reversed(list(rows.values())) if row.price is not None), None)
    spot_volume = sum(row.volume_24h_usd or 0 for row in rows.values() if row.market_type == "spot") or None
    perp_volume = sum(row.volume_24h_usd or 0 for row in rows.values() if row.market_type == "perp") or None
    return {
        "price": latest_price,
        "open_interest_usd": sum(row.open_interest_usd or 0 for row in rows.values()) or None,
        "volume_24h_usd": sum(row.volume_24h_usd or 0 for row in rows.values()) or None,
        "spot_volume_usd": spot_volume,
        "perp_volume_usd": perp_volume,
    }


def _aggregate_at_or_before(rows: list[MarketSnapshot], at_ts: datetime) -> dict[str, float | None]:
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
    return [change for _, change in window_changes_with_timestamps(rows, attr, minutes)]


def _oi_volume_ratio_points(rows: list[MarketSnapshot]) -> list[tuple[datetime, float]]:
    by_ts: dict[datetime, list[MarketSnapshot]] = defaultdict(list)
    for row in rows:
        by_ts[row.ts].append(row)
    points: list[tuple[datetime, float]] = []
    for ts, ts_rows in sorted(by_ts.items()):
        total_oi = sum(row.open_interest_usd or 0 for row in ts_rows) or None
        total_volume = sum(row.volume_24h_usd or 0 for row in ts_rows) or None
        ratio = safe_ratio(total_oi, total_volume)
        if ratio is not None:
            points.append((ts, ratio))
    return points


def _oi_volume_ratio_history(rows: list[MarketSnapshot]) -> list[float]:
    return [value for _, value in _oi_volume_ratio_points(rows)]


def _depth_total(row: OrderbookSnapshot) -> float:
    return (row.bid_depth_100bps_usd or 0) + (row.ask_depth_100bps_usd or 0)


def _latest_depth_total(rows: list[OrderbookSnapshot]) -> float | None:
    if not rows:
        return None
    return sum(_depth_total(row) for row in rows if row.ts == rows[-1].ts) or None


def _depth_totals(rows: list[OrderbookSnapshot]) -> list[float]:
    by_ts: dict[datetime, float] = defaultdict(float)
    for row in rows:
        by_ts[row.ts] += _depth_total(row)
    return list(by_ts.values())


def _depth_total_points(rows: list[OrderbookSnapshot]) -> list[tuple[datetime, float]]:
    by_ts: dict[datetime, float] = defaultdict(float)
    for row in rows:
        by_ts[row.ts] += _depth_total(row)
    return [(ts, value) for ts, value in sorted(by_ts.items()) if value]


def _depth_at_or_before(rows: list[OrderbookSnapshot], at_ts: datetime) -> float | None:
    eligible = [row for row in rows if row.ts <= at_ts]
    if not eligible:
        return None
    latest_ts = eligible[-1].ts
    return sum(_depth_total(row) for row in eligible if row.ts == latest_ts) or None


def _latest_weighted_imbalance(rows: list[OrderbookSnapshot]) -> float | None:
    if not rows:
        return None
    latest_ts = rows[-1].ts
    latest_rows = [row for row in rows if row.ts == latest_ts]
    return _weighted_imbalance(latest_rows)


def _imbalance_points(rows: list[OrderbookSnapshot]) -> list[tuple[datetime, float]]:
    grouped: dict[datetime, list[OrderbookSnapshot]] = defaultdict(list)
    for row in rows:
        grouped[row.ts].append(row)
    points: list[tuple[datetime, float]] = []
    for ts, ts_rows in sorted(grouped.items()):
        imbalance = _weighted_imbalance(ts_rows)
        if imbalance is not None:
            points.append((ts, imbalance))
    return points


def _weighted_imbalance(rows: list[OrderbookSnapshot]) -> float | None:
    total_weight = sum(_depth_total(row) for row in rows)
    if total_weight <= 0:
        return None
    return sum((row.imbalance_100bps or 0) * _depth_total(row) for row in rows) / total_weight


def _segmented_point_history(
    points: list[tuple[datetime, float]],
    current_segment: tuple[int, str, str],
    cutoff: datetime,
    min_observations: int = MIN_SEGMENT_OBSERVATIONS,
) -> tuple[list[float], str]:
    recent = [(ts, value) for ts, value in points if ts >= cutoff]
    if not recent:
        return [], "unsegmented_fallback"
    hour_block, day_type, btc_regime = current_segment
    exact = [value for ts, value in recent if get_segment(ts, btc_regime) == current_segment]
    if len(exact) >= min_observations:
        return exact, serialize_segment(current_segment)
    hour_day = [
        value
        for ts, value in recent
        if get_segment(ts, btc_regime)[0] == hour_block and get_segment(ts, btc_regime)[1] == day_type
    ]
    if len(hour_day) >= min_observations:
        return hour_day, f"{hour_block}:{day_type}:any_regime"
    hour = [value for ts, value in recent if get_segment(ts, btc_regime)[0] == hour_block]
    if len(hour) >= min_observations:
        return hour, f"{hour_block}:any_day:any_regime"
    return [], "unsegmented_fallback"


def _dex_buy_sell_ratio(latest_dex: DexSnapshot | None) -> float | None:
    if latest_dex is None or latest_dex.buys_1h is None or latest_dex.sells_1h is None:
        return None
    return safe_ratio(float(latest_dex.buys_1h), float(latest_dex.sells_1h))


def _funding_oi_divergent(latest_funding: float | None, oi_1h: float | None) -> float | None:
    if latest_funding is None or oi_1h is None:
        return None
    funding_direction = 1 if latest_funding > 0 else -1
    oi_direction = 1 if oi_1h > 0 else -1
    return 1.0 if funding_direction != oi_direction else 0.0


def _venue_share_features(latest_by_venue: dict[tuple[str, str], MarketSnapshot]) -> list[FeatureValue]:
    features: list[FeatureValue] = []
    total_oi = sum(row.open_interest_usd or 0 for row in latest_by_venue.values())
    total_volume = sum(row.volume_24h_usd or 0 for row in latest_by_venue.values())
    for (venue, market_type), row in latest_by_venue.items():
        if total_oi and row.open_interest_usd:
            features.append(
                FeatureValue(
                    "venue_oi_share",
                    "latest",
                    row.open_interest_usd / total_oi,
                    {"venue": venue, "market_type": market_type},
                )
            )
        if total_volume and row.volume_24h_usd:
            features.append(
                FeatureValue(
                    "venue_volume_share",
                    "latest",
                    row.volume_24h_usd / total_volume,
                    {"venue": venue, "market_type": market_type},
                )
            )
        if venue == "upbit" and total_volume and row.volume_24h_usd:
            features.append(
                FeatureValue("upbit_volume_share", "latest", row.volume_24h_usd / total_volume, {"venue": venue})
            )
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
        FeatureValue(
            "hl_liq_cluster_distance_pct",
            "nearest",
            distance,
            {"side": nearest.side, "market": nearest.market},
        ),
        FeatureValue(
            "hl_liq_cluster_size_usd",
            "nearest",
            nearest.cluster_notional_usd,
            {"side": nearest.side, "market": nearest.market},
        ),
        FeatureValue(
            "hl_liq_cluster_size_vs_volume",
            "nearest",
            nearest.cluster_notional_usd / volume_24h if volume_24h else None,
            {"side": nearest.side, "market": nearest.market},
        ),
    ]
