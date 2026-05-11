from __future__ import annotations

from app.anomalies.models import AlertCandidate, FeatureMap, metadata, preferred_value, value

DETECTOR = "silent_oi_build"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    oi_change_4h = value(features, "oi_change", "4h")
    oi_percentile = preferred_value(features, "oi_change_percentile", "seg_60d_1h", "90d_1h")
    price_change_4h = value(features, "price_change", "4h")
    volume_percentile = preferred_value(features, "volume_change_percentile", "seg_60d_1h", "90d_1h")
    venue_count = value(features, "supported_venue_count", "latest")

    if oi_change_4h is None or oi_change_4h <= 0:
        return []
    if oi_percentile is None or oi_percentile < 90:
        return []
    if price_change_4h is None or abs(price_change_4h) >= 3:
        return []
    if volume_percentile is None or volume_percentile >= 50:
        return []

    severity = "high" if oi_change_4h > 15 and venue_count is not None and venue_count <= 3 else "medium"
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="silent_oi_4h",
            title=f"{symbol} | Silent OI build | {severity.upper()}",
            message=(
                f"Open interest built {oi_change_4h:+.2f}% over 4h while price stayed quiet "
                f"({price_change_4h:+.2f}%) and volume remained below its median regime."
            ),
            interpretation=(
                "OI is building steadily while price and volume remain quiet. This pattern is "
                "consistent with informed positioning before an anticipated catalyst."
            ),
            metrics={
                "oi_change_4h": oi_change_4h,
                "oi_percentile": oi_percentile,
                "price_change_4h": price_change_4h,
                "volume_change_percentile": volume_percentile,
                "supported_venue_count": venue_count,
            },
            venues={"scope": "aggregate"},
            dexscreener_url=metadata(features, "dex_liquidity_usd", "latest").get("dexscreener_url"),
        )
    ]
