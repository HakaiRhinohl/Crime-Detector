from __future__ import annotations

from app.anomalies.models import AlertCandidate, FeatureMap, value

DETECTOR = "manipulable_structure"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    venue_count = value(features, "supported_venue_count", "latest")
    oi_pct = value(features, "oi_change_percentile", "90d_1h")
    depth_pct = value(features, "depth_100bps_percentile", "90d")
    dex_liq_change = value(features, "dex_liquidity_change", "1h")
    if venue_count is None or oi_pct is None:
        return []
    fragile = venue_count <= 3 or (depth_pct is not None and depth_pct <= 10) or (
        dex_liq_change is not None and dex_liq_change <= -25
    )
    if not fragile or oi_pct < 95:
        return []
    severity = "high" if oi_pct >= 97 else "medium"
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="fragile_structure_oi",
            title=f"{symbol} | Manipulable structure | {severity.upper()}",
            message="Limited venue coverage or compressed liquidity is combining with abnormal OI activity.",
            interpretation="The asset has limited arbitrage venues and liquidity is compressing while leverage builds.",
            metrics={
                "supported_venue_count": venue_count,
                "oi_percentile_90d": oi_pct,
                "depth_percentile_90d": depth_pct,
                "dex_liquidity_change_1h": dex_liq_change,
            },
            venues={"scope": "aggregate"},
        )
    ]

