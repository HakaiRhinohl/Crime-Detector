from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.formatter import format_telegram_alert
from app.alerts.telegram import send_telegram_message
from app.anomalies.engine import filter_candidates_with_cooldown, generate_candidates
from app.anomalies.models import AlertCandidate
from app.config.settings import get_settings
from app.config.thresholds import TELEGRAM_SEVERITIES
from app.db.models import Alert, Asset, AssetDataCoverage
from app.utils.time import utc_now


async def process_alerts(session: AsyncSession) -> int:
    candidates = await filter_candidates_with_cooldown(session, await generate_candidates(session))
    sent = 0
    for candidate in candidates:
        telegram_sent = await maybe_send_telegram(session, candidate)
        await persist_candidate(session, candidate, telegram_sent)
        if telegram_sent:
            sent += 1
    await session.commit()
    return sent


async def maybe_send_telegram(session: AsyncSession, candidate: AlertCandidate) -> bool:
    settings = get_settings()
    if candidate.severity not in TELEGRAM_SEVERITIES and candidate.severity != "critical":
        return False
    if candidate.severity != "critical":
        sent_today = await count_sent_today(session)
        if sent_today >= settings.telegram_daily_cap:
            return False

    asset = await session.get(Asset, candidate.asset_id)
    coverage = (
        await session.execute(select(AssetDataCoverage).where(AssetDataCoverage.asset_id == candidate.asset_id))
    ).scalar_one_or_none()
    message = format_telegram_alert(
        candidate,
        symbol=asset.symbol if asset else str(candidate.asset_id),
        spot_venues=coverage.spot_venues if coverage else [],
        perp_venues=coverage.perp_venues if coverage else [],
    )
    return await send_telegram_message(message)


async def persist_candidate(
    session: AsyncSession, candidate: AlertCandidate, telegram_sent: bool
) -> None:
    stmt = insert(Alert).values(
        ts=utc_now(),
        asset_id=candidate.asset_id,
        detector=candidate.detector,
        severity=candidate.severity,
        title=candidate.title,
        message=candidate.message,
        interpretation=candidate.interpretation,
        venues=candidate.venues,
        metrics=candidate.metrics,
        dexscreener_url=candidate.dexscreener_url,
        telegram_sent=telegram_sent,
    )
    await session.execute(stmt)


async def count_sent_today(session: AsyncSession) -> int:
    since = utc_now() - timedelta(hours=24)
    return (
        await session.execute(
            select(func.count(Alert.id)).where(Alert.telegram_sent.is_(True), Alert.ts >= since)
        )
    ).scalar_one()
