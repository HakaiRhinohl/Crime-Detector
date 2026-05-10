from __future__ import annotations

from app.anomalies.models import AlertCandidate, FeatureMap, severity_from_percentile, value

DETECTOR = "perp_driven_pump"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    price_change = value(features, "price_change", "1h")
    price_percentile = value(features, "price_change_percentile", "90d_1h")
    oi_percentile = value(features, "oi_change_percentile", "90d_1h")
    oi_change = value(features, "oi_change", "1h")
    if (
        price_change is None
        or price_percentile is None
        or oi_percentile is None
        or price_percentile < 95
        or oi_percentile < 95
    ):
        return []
    severity = severity_from_percentile(max(price_percentile, oi_percentile))
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="aggregate_perp_price_oi_1h",
            title=f"{symbol} | Perp-driven pump structure | {severity.upper()}",
            message=f"Price changed {price_change:+.2f}% in 1h while OI changed {oi_change or 0:+.2f}%.",
            interpretation="Move appears leverage-driven rather than broad spot-driven.",
            metrics={
                "price_change_1h": price_change,
                "price_percentile_90d": price_percentile,
                "oi_percentile_90d": oi_percentile,
            },
            venues={"scope": "aggregate"},
        )
    ]

