from __future__ import annotations

from app.anomalies.models import AlertCandidate, FeatureMap, value

DETECTOR = "hyperliquid_liquidation_cluster"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    distance = value(features, "hl_liq_cluster_distance_pct", "nearest")
    size = value(features, "hl_liq_cluster_size_usd", "nearest")
    size_vs_volume = value(features, "hl_liq_cluster_size_vs_volume", "nearest")
    if distance is None or size is None:
        return []
    if abs(distance) > 3 or size < 250_000:
        return []
    severity = "critical" if abs(distance) <= 1 and (size_vs_volume or 0) >= 0.2 else "high"
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="nearest_hl_liq_cluster",
            title=f"{symbol} | Hyperliquid liquidation cluster | {severity.upper()}",
            message=f"Hyperliquid liquidation cluster ${size:,.0f} is {distance:+.2f}% from current price.",
            interpretation="Price is approaching a meaningful Hyperliquid liquidation zone.",
            metrics={"cluster_distance_pct": distance, "cluster_size_usd": size, "cluster_size_vs_volume": size_vs_volume},
            venues={"primary": "hyperliquid"},
        )
    ]

