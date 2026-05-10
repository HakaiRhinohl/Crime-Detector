from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.anomalies.models import AlertCandidate
from app.config.thresholds import MATERIAL_WORSENING_RATIO, SEVERITY_RANK
from app.db.models import AlertState
from app.utils.time import utc_now


def candidate_metric_value(candidate: AlertCandidate) -> float | None:
    for key in [
        "oi_change_1h",
        "cluster_size_usd",
        "dex_liquidity_change_1h",
        "depth_percentile_90d",
        "upbit_volume_share",
    ]:
        value = candidate.metrics.get(key)
        if isinstance(value, int | float):
            return abs(float(value))
    return None


async def should_send(session: AsyncSession, candidate: AlertCandidate) -> bool:
    state = (
        await session.execute(
            select(AlertState).where(
                AlertState.asset_id == candidate.asset_id,
                AlertState.detector == candidate.detector,
                AlertState.event_key == candidate.event_key,
            )
        )
    ).scalar_one_or_none()
    if state is None:
        return True

    new_rank = SEVERITY_RANK.get(candidate.severity, 0)
    old_rank = SEVERITY_RANK.get(state.last_severity or "low", 0)
    if new_rank > old_rank:
        return True

    metric = candidate_metric_value(candidate)
    if metric is not None and state.last_metric_value:
        if metric >= abs(state.last_metric_value) * MATERIAL_WORSENING_RATIO:
            return True

    if state.last_alert_ts and state.last_alert_ts < utc_now() - timedelta(hours=12):
        return candidate.severity in {"high", "critical"}
    return False


async def update_state(session: AsyncSession, candidate: AlertCandidate) -> None:
    metric = candidate_metric_value(candidate)
    stmt = (
        insert(AlertState)
        .values(
            asset_id=candidate.asset_id,
            detector=candidate.detector,
            event_key=candidate.event_key,
            last_alert_ts=utc_now(),
            last_severity=candidate.severity,
            last_metric_value=metric,
            metadata_=candidate.metrics,
        )
        .on_conflict_do_update(
            index_elements=[AlertState.asset_id, AlertState.detector, AlertState.event_key],
            set_={
                "last_alert_ts": utc_now(),
                "last_severity": candidate.severity,
                "last_metric_value": metric,
                "metadata": candidate.metrics,
            },
        )
    )
    await session.execute(stmt)

