from __future__ import annotations

from app.anomalies.models import AlertCandidate, FeatureMap, value

DETECTOR = "cex_depth_compression"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    depth_pct = value(features, "depth_100bps_percentile", "90d")
    depth_multiple = value(features, "depth_100bps_median_multiple", "90d")
    depth_change = value(features, "depth_100bps_change", "1h")
    oi_pct = value(features, "oi_change_percentile", "90d_1h")
    price_pct = value(features, "price_change_percentile", "90d_1h")
    thin = (depth_pct is not None and depth_pct <= 5) or (
        depth_multiple is not None and depth_multiple <= 0.5
    )
    active = (oi_pct or 0) >= 95 or (price_pct or 0) >= 95
    if not thin or not active:
        return []
    severity = "high" if (depth_pct or 100) <= 3 or (oi_pct or 0) >= 97 else "medium"
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="cex_depth_100bps",
            title=f"{symbol} | CEX depth compression | {severity.upper()}",
            message=f"CEX depth is historically thin while activity is increasing. Depth changed {depth_change or 0:+.2f}% in 1h.",
            interpretation="CEX liquidity is thinning while activity is increasing.",
            metrics={"depth_percentile_90d": depth_pct, "depth_median_multiple_90d": depth_multiple, "oi_percentile_90d": oi_pct},
            venues={"scope": "cex"},
        )
    ]

