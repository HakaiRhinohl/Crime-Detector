from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Asset, MarketSnapshot

STRONG_DOWN = "strong_down"
DOWN = "down"
FLAT = "flat"
UP = "up"
STRONG_UP = "strong_up"
BTC_REGIME_BUCKETS = {STRONG_DOWN, DOWN, FLAT, UP, STRONG_UP}


@dataclass(frozen=True)
class BTCRegime:
    return_7d: float | None
    bucket: str


def bucket_btc_regime(return_7d: float | None) -> str:
    if return_7d is None:
        return FLAT
    if return_7d < -0.07:
        return STRONG_DOWN
    if return_7d < -0.02:
        return DOWN
    if return_7d <= 0.02:
        return FLAT
    if return_7d <= 0.07:
        return UP
    return STRONG_UP


async def compute_btc_regime(session: AsyncSession, ts: datetime) -> BTCRegime:
    asset = (await session.execute(select(Asset).where(Asset.symbol == "BTC"))).scalar_one_or_none()
    if asset is None:
        return BTCRegime(return_7d=None, bucket=FLAT)

    now_price = await _btc_price_at_or_before(session, asset.id, ts)
    previous_price = await _btc_price_at_or_before(session, asset.id, ts - timedelta(days=7))
    if now_price is None or previous_price is None or previous_price <= 0:
        return BTCRegime(return_7d=None, bucket=FLAT)

    return_7d = (now_price / previous_price) - 1.0
    return BTCRegime(return_7d=return_7d, bucket=bucket_btc_regime(return_7d))


async def _btc_price_at_or_before(session: AsyncSession, asset_id: int, ts: datetime) -> float | None:
    return (
        await session.execute(
            select(MarketSnapshot.price)
            .where(MarketSnapshot.asset_id == asset_id)
            .where(MarketSnapshot.price.is_not(None))
            .where(MarketSnapshot.ts <= ts)
            .order_by(MarketSnapshot.ts.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def get_segment(ts: datetime, btc_regime: str) -> tuple[int, str, str]:
    """Returns (hour_block, day_type, btc_regime)."""
    hour_block = ts.hour // 4
    day_type = "weekend" if ts.weekday() >= 5 else "weekday"
    regime = btc_regime if btc_regime in BTC_REGIME_BUCKETS else FLAT
    return hour_block, day_type, regime


def serialize_segment(segment: tuple[int, str, str]) -> str:
    return f"{segment[0]}:{segment[1]}:{segment[2]}"

