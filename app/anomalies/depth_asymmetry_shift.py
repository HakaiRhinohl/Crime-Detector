from __future__ import annotations

from app.anomalies.models import AlertCandidate, FeatureMap, preferred_value, value

DETECTOR = "depth_asymmetry_shift"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    imbalance = value(features, "depth_imbalance_100bps", "latest")
    imbalance_pct = preferred_value(features, "depth_imbalance_percentile", "seg_60d", "90d")
    oi_pct = preferred_value(features, "oi_change_percentile", "seg_60d_1h", "90d_1h")
    price_pct = preferred_value(features, "price_change_percentile", "seg_60d_1h", "90d_1h")

    if imbalance is None or abs(imbalance) < 0.4:
        return []
    if imbalance_pct is None or (5 < imbalance_pct < 95):
        return []
    if (oi_pct or 0) < 90 and (price_pct or 0) < 90:
        return []

    severity = "high" if abs(imbalance) >= 0.6 else "medium"
    if imbalance < 0:
        interpretation = (
            "Ask-side depth is dominating. Bid support has been pulled. Combined with active "
            "positioning, this may precede a downward move."
        )
    else:
        interpretation = (
            "Bid-side depth is dominating. Ask-side liquidity has thinned. Combined with active "
            "positioning, this may precede an upward squeeze."
        )
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="depth_imbalance_shift",
            title=f"{symbol} | Depth asymmetry shift | {severity.upper()}",
            message=(
                f"Orderbook imbalance at +/-1% is {imbalance:+.2f}, at p{imbalance_pct:.0f} "
                "for its comparable history."
            ),
            interpretation=interpretation,
            metrics={
                "depth_imbalance_100bps": imbalance,
                "depth_imbalance_percentile": imbalance_pct,
                "oi_percentile": oi_pct,
                "price_percentile": price_pct,
            },
            venues={"scope": "cex"},
        )
    ]
