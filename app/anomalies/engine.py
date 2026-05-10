from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.anomalies import (
    cex_depth_compression,
    dex_liquidity_compression,
    hyperliquid_liquidation_cluster,
    manipulable_structure,
    oi_build_up,
    perp_driven_pump,
    upbit_led_move,
    venue_specific,
)
from app.anomalies.models import AlertCandidate, FeatureMap
from app.db.models import Asset, Feature

DETECTORS = [
    oi_build_up.detect,
    perp_driven_pump.detect,
    venue_specific.detect,
    manipulable_structure.detect,
    dex_liquidity_compression.detect,
    cex_depth_compression.detect,
    upbit_led_move.detect,
    hyperliquid_liquidation_cluster.detect,
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


async def load_latest_features(session: AsyncSession) -> dict[int, FeatureMap]:
    rows = (
        await session.execute(
            select(Feature).order_by(Feature.asset_id, Feature.feature_name, Feature.window, Feature.ts.desc())
        )
    ).scalars().all()
    out: dict[int, FeatureMap] = defaultdict(dict)
    seen: set[tuple[int, str, str]] = set()
    for row in rows:
        key = (row.asset_id, row.feature_name, row.window)
        if key in seen:
            continue
        seen.add(key)
        out[row.asset_id][(row.feature_name, row.window)] = (row.value, row.metadata_ or {})
    return out

