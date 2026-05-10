from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, MarketSnapshot


@dataclass(frozen=True)
class AlertOutcome:
    alert_id: int
    max_abs_return_1h: float | None
    max_abs_return_4h: float | None
    max_abs_return_24h: float | None
    volume_expansion_after_alert: float | None


async def evaluate_alert(session: AsyncSession, alert: Alert) -> AlertOutcome:
    rows = (
        await session.execute(
            select(MarketSnapshot)
            .where(MarketSnapshot.asset_id == alert.asset_id)
            .where(MarketSnapshot.ts >= alert.ts)
            .where(MarketSnapshot.ts <= alert.ts + timedelta(hours=24))
            .order_by(MarketSnapshot.ts)
        )
    ).scalars().all()
    base_price = next((row.price for row in rows if row.price), None)
    base_volume = next((row.volume_24h_usd for row in rows if row.volume_24h_usd), None)
    return AlertOutcome(
        alert_id=alert.id,
        max_abs_return_1h=_max_abs_return(rows, base_price, alert.ts + timedelta(hours=1)),
        max_abs_return_4h=_max_abs_return(rows, base_price, alert.ts + timedelta(hours=4)),
        max_abs_return_24h=_max_abs_return(rows, base_price, alert.ts + timedelta(hours=24)),
        volume_expansion_after_alert=_volume_expansion(rows, base_volume),
    )


def _max_abs_return(rows: list[MarketSnapshot], base_price: float | None, end_ts) -> float | None:
    if not base_price:
        return None
    returns = [abs(((row.price - base_price) / base_price) * 100) for row in rows if row.ts <= end_ts and row.price]
    return max(returns) if returns else None


def _volume_expansion(rows: list[MarketSnapshot], base_volume: float | None) -> float | None:
    if not base_volume:
        return None
    values = [row.volume_24h_usd for row in rows if row.volume_24h_usd]
    return max(values) / base_volume if values else None

