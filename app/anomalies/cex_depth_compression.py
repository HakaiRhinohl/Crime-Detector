from __future__ import annotations

from app.anomalies.models import AlertCandidate, FeatureMap, preferred_value, value

DETECTOR = "cex_depth_compression"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    depth_pct = preferred_value(features, "depth_100bps_percentile", "seg_60d", "90d")
    depth_multiple = value(features, "depth_100bps_median_multiple", "90d")
    depth_change = value(features, "depth_100bps_change", "1h")
    oi_pct = preferred_value(features, "oi_change_percentile", "seg_60d_1h", "90d_1h")
    price_pct = preferred_value(features, "price_change_percentile", "seg_60d_1h", "90d_1h")
    depth_imbalance = value(features, "depth_imbalance_100bps", "latest")
    thin = (depth_pct is not None and depth_pct <= 5) or (
        depth_multiple is not None and depth_multiple <= 0.5
    )
    active = (oi_pct or 0) >= 95 or (price_pct or 0) >= 95
    if not thin or not active:
        return []
    severity = "high" if (depth_pct or 100) <= 3 or (oi_pct or 0) >= 97 else "medium"
    if depth_imbalance is not None and depth_imbalance < -0.4:
        severity = "critical" if severity == "high" else "high"
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="cex_depth_100bps",
            title=f"{symbol} | CEX depth compression | {severity.upper()}",
            message=(
                "CEX depth is historically thin while activity is increasing. "
                f"Depth changed {depth_change or 0:+.2f}% in 1h and imbalance is "
                f"{depth_imbalance or 0:+.2f}."
            ),
            interpretation="CEX liquidity is thinning while activity is increasing.",
            metrics={
                "depth_percentile": depth_pct,
                "depth_median_multiple_90d": depth_multiple,
                "depth_imbalance_100bps": depth_imbalance,
                "oi_percentile": oi_pct,
                "price_percentile": price_pct,
            },
            venues={"scope": "cex"},
        )
    ]
