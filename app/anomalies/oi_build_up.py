from __future__ import annotations

from app.anomalies.models import (
    AlertCandidate,
    FeatureMap,
    metadata,
    severity_from_percentile,
    value,
)

DETECTOR = "oi_build_up"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    oi_change = value(features, "oi_change", "1h")
    oi_percentile = value(features, "oi_change_percentile", "90d_1h")
    oi_multiple = value(features, "oi_change_median_multiple", "90d_1h")
    price_change = value(features, "price_change", "1h")
    funding_pct = value(features, "funding_percentile", "90d")
    depth_change = value(features, "depth_100bps_change", "1h")
    dex_liq_change = value(features, "dex_liquidity_change", "1h")
    venue_count = value(features, "supported_venue_count", "latest")

    if oi_change is None or oi_percentile is None or oi_multiple is None:
        return []
    if oi_percentile < 95 or oi_multiple < 2:
        return []
    if price_change is not None and abs(price_change) >= 12 and oi_percentile < 99:
        return []

    confirmations = [
        funding_pct is not None and funding_pct >= 90,
        depth_change is not None and depth_change <= -25,
        dex_liq_change is not None and dex_liq_change <= -20,
        venue_count is not None and venue_count <= 3,
    ]
    severity = severity_from_percentile(oi_percentile)
    if severity == "medium" and sum(confirmations) >= 2:
        severity = "high"

    metrics = {
        "oi_change_1h": oi_change,
        "oi_percentile_90d": oi_percentile,
        "oi_median_multiple_90d": oi_multiple,
        "price_change_1h": price_change,
        "funding_percentile_90d": funding_pct,
        "depth_change_1h": depth_change,
        "dex_liquidity_change_1h": dex_liq_change,
    }
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="aggregate_oi_1h",
            title=f"{symbol} | OI build-up | {severity.upper()}",
            message=(
                f"Open interest changed {oi_change:+.2f}% in 1h and is at p{oi_percentile:.0f} "
                f"of its 90d 1h history while price moved {price_change or 0:+.2f}%."
            ),
            interpretation="Possible positioning build-up before volatility expansion.",
            metrics=metrics,
            venues={"scope": "aggregate"},
            dexscreener_url=metadata(features, "dex_liquidity_usd", "latest").get("dexscreener_url"),
        )
    ]

