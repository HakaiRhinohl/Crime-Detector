from __future__ import annotations

from app.anomalies.models import AlertCandidate, FeatureMap, preferred_value, value

DETECTOR = "funding_oi_divergence"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    divergent = value(features, "funding_oi_divergent", "latest")
    oi_percentile = preferred_value(features, "oi_change_percentile", "seg_60d_1h", "90d_1h")
    funding_percentile = value(features, "funding_percentile", "90d")
    oi_change = value(features, "oi_change", "1h")
    funding_rate = value(features, "funding_current", "latest")

    if divergent != 1.0:
        return []
    if oi_percentile is None or oi_percentile < 95:
        return []
    if funding_percentile is None or (10 < funding_percentile < 90):
        return []

    severity = "high" if oi_percentile >= 97 else "medium"
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="funding_oi_divergence",
            title=f"{symbol} | Funding/OI divergence | {severity.upper()}",
            message=(
                f"Funding percentile is p{funding_percentile:.0f} while OI change is "
                f"p{oi_percentile:.0f}; their directions diverge."
            ),
            interpretation=(
                "Funding rate and OI change are moving in opposite directions at extreme levels. "
                "This suggests aggressive one-sided positioning that may be hedged off-venue."
            ),
            metrics={
                "funding_oi_divergent": divergent,
                "funding_percentile_90d": funding_percentile,
                "funding_rate": funding_rate,
                "oi_percentile": oi_percentile,
                "oi_change_1h": oi_change,
            },
            venues={"scope": "aggregate"},
        )
    ]
