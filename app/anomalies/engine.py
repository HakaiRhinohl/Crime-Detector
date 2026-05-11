from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.anomalies import (
    cex_depth_compression,
    depth_asymmetry_shift,
    dex_liquidity_compression,
    funding_oi_divergence,
    hyperliquid_liquidation_cluster,
    manipulable_structure,
    oi_build_up,
    perp_driven_pump,
    silent_oi_build,
    upbit_led_move,
    venue_specific,
)
from app.anomalies.models import AlertCandidate, FeatureMap
from app.db.models import AlertState, Asset, Feature
from app.utils.time import utc_now

COOLDOWN_MINUTES = {
    "critical": 15,  # TUNABLE: adjust based on alert volume
    "high": 30,  # TUNABLE: adjust based on alert volume
    "medium": 60,  # TUNABLE: adjust based on alert volume
    "low": 120,  # TUNABLE: adjust based on alert volume
}

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

DETECTORS = [
    oi_build_up.detect,
    perp_driven_pump.detect,
    venue_specific.detect,
    manipulable_structure.detect,
    dex_liquidity_compression.detect,
    cex_depth_compression.detect,
    upbit_led_move.detect,
    hyperliquid_liquidation_cluster.detect,
    silent_oi_build.detect,
    depth_asymmetry_shift.detect,
    funding_oi_divergence.detect,
]


async def generate_candidates(session: AsyncSession) -> list[AlertCandidate]:
    assets = (await session.execute(select(Asset).where(Asset.is_active.is_(True)))).scalars().all()
    latest_features = await load_latest_features(session)
    candidates: list[AlertCandidate] = []
    for asset in assets:
        features = latest_features.get(asset.id, {})
        if not features:
            continue
        for detector in DETECTORS:
            candidates.extend(detector(asset.id, asset.symbol, features))
    return candidates


async def filter_candidates_with_cooldown(
    session: AsyncSession,
    candidates: list[AlertCandidate],
) -> list[AlertCandidate]:
    now = utc_now()
    allowed: list[AlertCandidate] = []
    for candidate in candidates:
        if await _cooldown_allows(session, candidate, now):
            await _upsert_alert_state(session, candidate, now)
            allowed.append(candidate)
    return _enrich_multi_detector_notes(allowed)


async def _cooldown_allows(session: AsyncSession, candidate: AlertCandidate, now) -> bool:
    state = (
        await session.execute(
            select(AlertState).where(
                AlertState.asset_id == candidate.asset_id,
                AlertState.detector == candidate.detector,
                AlertState.event_key == candidate.event_key,
            )
        )
    ).scalar_one_or_none()
    if state is None or state.last_alert_ts is None:
        return True

    old_rank = SEVERITY_ORDER.get(state.last_severity or "low", 0)
    new_rank = SEVERITY_ORDER.get(candidate.severity, 0)
    if new_rank > old_rank:
        return True

    cooldown = timedelta(minutes=COOLDOWN_MINUTES.get(candidate.severity, COOLDOWN_MINUTES["low"]))
    return now - state.last_alert_ts >= cooldown


async def _upsert_alert_state(session: AsyncSession, candidate: AlertCandidate, now) -> None:
    metric = _candidate_metric_value(candidate)
    stmt = (
        insert(AlertState)
        .values(
            asset_id=candidate.asset_id,
            detector=candidate.detector,
            event_key=candidate.event_key,
            last_alert_ts=now,
            last_severity=candidate.severity,
            last_metric_value=metric,
            metadata_=candidate.metrics,
        )
        .on_conflict_do_update(
            index_elements=[AlertState.asset_id, AlertState.detector, AlertState.event_key],
            set_={
                "last_alert_ts": now,
                "last_severity": candidate.severity,
                "last_metric_value": metric,
                "metadata": candidate.metrics,
            },
        )
    )
    await session.execute(stmt)


def _candidate_metric_value(candidate: AlertCandidate) -> float | None:
    for key in [
        "oi_change_1h",
        "oi_change_4h",
        "oi_zscore",
        "zscore",
        "cluster_size_usd",
        "dex_liquidity_change_1h",
        "depth_percentile",
        "depth_percentile_90d",
        "depth_imbalance_100bps",
        "upbit_volume_share",
        "venue_oi_share",
        "venue_volume_share",
    ]:
        metric_value = candidate.metrics.get(key)
        if isinstance(metric_value, int | float):
            return abs(float(metric_value))
    return None


def _enrich_multi_detector_notes(candidates: list[AlertCandidate]) -> list[AlertCandidate]:
    detectors_by_asset: dict[int, list[str]] = defaultdict(list)
    for candidate in candidates:
        detectors_by_asset[candidate.asset_id].append(candidate.detector)
    enriched: list[AlertCandidate] = []
    for candidate in candidates:
        detectors = sorted(set(detectors_by_asset[candidate.asset_id]))
        if len(detectors) <= 1:
            enriched.append(candidate)
            continue
        note = f"\n\n⚠️ Multiple detectors triggered: {', '.join(detectors)}"
        enriched.append(replace(candidate, message=f"{candidate.message}{note}"))
    return enriched


async def load_latest_features(session: AsyncSession) -> dict[int, FeatureMap]:
    latest_ts = (await session.execute(select(func.max(Feature.ts)))).scalar_one_or_none()
    if latest_ts is None:
        return {}
    rows = (
        await session.execute(
            select(Feature).where(Feature.ts == latest_ts).order_by(Feature.asset_id, Feature.feature_name, Feature.window)
        )
    ).scalars().all()
    out: dict[int, FeatureMap] = defaultdict(dict)
    for row in rows:
        out[row.asset_id][(row.feature_name, row.window)] = (row.value, row.metadata_ or {})
    return out
