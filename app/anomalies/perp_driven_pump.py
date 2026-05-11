from __future__ import annotations

from app.anomalies.models import (
    AlertCandidate,
    FeatureMap,
    preferred_value,
    severity_from_percentile,
    value,
)

DETECTOR = "perp_driven_pump"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    price_change = value(features, "price_change", "1h")
    price_percentile = preferred_value(features, "price_change_percentile", "seg_60d_1h", "90d_1h")
    oi_percentile = preferred_value(features, "oi_change_percentile", "seg_60d_1h", "90d_1h")
    oi_change = value(features, "oi_change", "1h")
    perp_spot_ratio = value(features, "perp_spot_volume_ratio", "latest")
    if (
        price_change is None
        or price_percentile is None
        or oi_percentile is None
        or price_percentile < 95
        or oi_percentile < 95
        or price_change <= 0
        or oi_change is None
        or oi_change <= 0
    ):
        return []
    severity = severity_from_percentile(max(price_percentile, oi_percentile))
    if severity == "medium" and perp_spot_ratio is not None and perp_spot_ratio > 3.0:
        severity = "high"
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="aggregate_perp_price_oi_1h",
            title=f"{symbol} | Perp-driven pump structure | {severity.upper()}",
            message=(
                f"Price changed {price_change:+.2f}% in 1h while OI changed {oi_change or 0:+.2f}%. "
                f"Perp/spot volume ratio is {perp_spot_ratio or 0:.2f}."
            ),
            interpretation="Move appears leverage-driven rather than broad spot-driven.",
            metrics={
                "price_change_1h": price_change,
                "price_percentile": price_percentile,
                "oi_percentile": oi_percentile,
                "perp_spot_volume_ratio": perp_spot_ratio,
            },
            venues={"scope": "aggregate"},
        )
    ]
