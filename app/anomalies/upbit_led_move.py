from __future__ import annotations

from app.anomalies.models import AlertCandidate, FeatureMap, preferred_value, value

DETECTOR = "upbit_led_move"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    share = value(features, "upbit_volume_share", "latest")
    price_pct = preferred_value(features, "price_change_percentile", "seg_60d_1h", "90d_1h")
    volume_pct = preferred_value(features, "volume_change_percentile", "seg_60d_1h", "90d_1h")
    if share is None or share < 0.55:
        return []
    if max(price_pct or 0, volume_pct or 0) < 95:
        return []
    severity = "high" if share >= 0.75 or (price_pct or 0) >= 97 else "medium"
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="upbit_volume_share",
            title=f"{symbol} | Upbit-led move | {severity.upper()}",
            message=f"Upbit accounts for {share:.0%} of latest venue volume.",
            interpretation="Move appears concentrated in Korean spot flow. Watch for perp catch-up or fade.",
            metrics={
                "upbit_volume_share": share,
                "price_percentile": price_pct,
                "volume_change_percentile": volume_pct,
            },
            venues={"primary": "upbit"},
        )
    ]
