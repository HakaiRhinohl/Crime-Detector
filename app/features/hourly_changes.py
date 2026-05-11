from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HourlyChange, MarketSnapshot
from app.features.rolling_windows import pct_change
from app.features.segmentation import get_segment, serialize_segment

HOURLY_CHANGE_METRICS = ("open_interest_usd", "price", "volume_24h_usd")
MIN_SEGMENT_OBSERVATIONS = 20  # TUNABLE: minimum samples before trusting segmented percentiles


async def upsert_hourly_changes_for_asset(
    session: AsyncSession,
    asset_id: int,
    ts: datetime,
    rows: list[MarketSnapshot],
    btc_regime: str,
) -> int:
    values = hourly_change_rows_for_asset(asset_id, ts, rows, btc_regime)
    await upsert_hourly_change_rows(session, values)
    return len(values)


def hourly_change_rows_for_asset(
    asset_id: int,
    ts: datetime,
    rows: list[MarketSnapshot],
    btc_regime: str,
) -> list[dict]:
    current = _aggregate_at_or_before(rows, ts)
    previous = _aggregate_at_or_before(rows, ts - timedelta(hours=1))
    hour_block, day_type, regime = get_segment(ts, btc_regime)
    values: list[dict] = []
    for metric in HOURLY_CHANGE_METRICS:
        change = pct_change(current.get(metric), previous.get(metric))
        values.append(
            dict(
                asset_id=asset_id,
                ts=ts,
                metric=metric,
                pct_change=change,
                hour_block=hour_block,
                day_type=day_type,
                btc_regime=regime,
            )
        )
    return values


async def upsert_hourly_change_rows(session: AsyncSession, rows: list[dict]) -> int:
    if not rows:
        return 0
    deduped = {
        (row["asset_id"], row["ts"], row["metric"]): row
        for row in rows
    }
    values = list(deduped.values())
    for chunk_start in range(0, len(values), 3000):
        chunk = values[chunk_start : chunk_start + 3000]
        stmt = insert(HourlyChange).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[HourlyChange.asset_id, HourlyChange.ts, HourlyChange.metric],
            set_={
                "pct_change": stmt.excluded.pct_change,
                "hour_block": stmt.excluded.hour_block,
                "day_type": stmt.excluded.day_type,
                "btc_regime": stmt.excluded.btc_regime,
            },
        )
        await session.execute(stmt)
    return len(deduped)


async def hourly_change_history(
    session: AsyncSession,
    asset_id: int,
    metric: str,
    ts: datetime,
    *,
    days: int,
) -> list[float]:
    rows = (
        await session.execute(
            select(HourlyChange.pct_change)
            .where(HourlyChange.asset_id == asset_id)
            .where(HourlyChange.metric == metric)
            .where(HourlyChange.ts >= ts - timedelta(days=days))
            .where(HourlyChange.ts < ts)
            .where(HourlyChange.pct_change.is_not(None))
            .order_by(HourlyChange.ts)
        )
    ).all()
    return [float(row[0]) for row in rows if row[0] is not None]


async def segmented_hourly_change_history(
    session: AsyncSession,
    asset_id: int,
    metric: str,
    ts: datetime,
    current_segment: tuple[int, str, str],
    *,
    days: int,
    min_observations: int = MIN_SEGMENT_OBSERVATIONS,
) -> tuple[list[float], str]:
    hour_block, day_type, btc_regime = current_segment
    base = (
        select(HourlyChange.pct_change)
        .where(HourlyChange.asset_id == asset_id)
        .where(HourlyChange.metric == metric)
        .where(HourlyChange.ts >= ts - timedelta(days=days))
        .where(HourlyChange.ts < ts)
        .where(HourlyChange.pct_change.is_not(None))
    )

    attempts = [
        (
            base.where(
                HourlyChange.hour_block == hour_block,
                HourlyChange.day_type == day_type,
                HourlyChange.btc_regime == btc_regime,
            ),
            serialize_segment(current_segment),
        ),
        (
            base.where(HourlyChange.hour_block == hour_block, HourlyChange.day_type == day_type),
            f"{hour_block}:{day_type}:any_regime",
        ),
        (
            base.where(HourlyChange.hour_block == hour_block),
            f"{hour_block}:any_day:any_regime",
        ),
    ]
    for query, label in attempts:
        rows = (await session.execute(query.order_by(HourlyChange.ts))).all()
        values = [float(row[0]) for row in rows if row[0] is not None]
        if len(values) >= min_observations:
            return values, label
    return [], "unsegmented_fallback"


def _aggregate_at_or_before(rows: list[MarketSnapshot], at_ts: datetime) -> dict[str, float | None]:
    by_venue: dict[tuple[str, str], MarketSnapshot] = {}
    for row in rows:
        if row.ts <= at_ts:
            by_venue[(row.venue, row.market_type)] = row
    return _aggregate_latest_market(by_venue)


def _aggregate_latest_market(rows: dict[tuple[str, str], MarketSnapshot]) -> dict[str, float | None]:
    latest_price = next((row.price for row in reversed(list(rows.values())) if row.price is not None), None)
    return {
        "price": latest_price,
        "open_interest_usd": sum(row.open_interest_usd or 0 for row in rows.values()) or None,
        "volume_24h_usd": sum(row.volume_24h_usd or 0 for row in rows.values()) or None,
    }


def window_changes_with_timestamps(
    rows: list[MarketSnapshot],
    attr: str,
    minutes: int,
) -> list[tuple[datetime, float]]:
    grouped: dict[tuple[str, str], list[MarketSnapshot]] = defaultdict(list)
    for row in rows:
        grouped[(row.venue, row.market_type)].append(row)
    changes: list[tuple[datetime, float]] = []
    for series in grouped.values():
        for idx, row in enumerate(series):
            previous_ts = row.ts - timedelta(minutes=minutes)
            previous = next((item for item in reversed(series[:idx]) if item.ts <= previous_ts), None)
            change = pct_change(getattr(row, attr), getattr(previous, attr) if previous else None)
            if change is not None:
                changes.append((row.ts, change))
    return changes
