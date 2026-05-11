from __future__ import annotations

from app.anomalies.models import (
    AlertCandidate,
    FeatureMap,
    either_gate_trigger,
    metadata,
    preferred_value,
    value,
)

DETECTOR = "oi_build_up"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    oi_change = value(features, "oi_change", "1h")
    oi_percentile = preferred_value(features, "oi_change_percentile", "seg_60d_1h", "90d_1h")
    oi_zscore = value(features, "oi_change_zscore", "ewma_1h")
    oi_multiple = value(features, "oi_change_median_multiple", "90d_1h")
    price_change = value(features, "price_change", "1h")
    funding_pct = value(features, "funding_percentile", "90d")
    depth_change = value(features, "depth_100bps_change", "1h")
    dex_liq_change = value(features, "dex_liquidity_change", "1h")
    volume_pct = preferred_value(features, "volume_change_percentile", "seg_60d_1h", "90d_1h")
    venue_count = value(features, "supported_venue_count", "latest")

    if oi_change is None or oi_change <= 0:
        return []
    trigger, severity = either_gate_trigger(oi_percentile, oi_zscore, percentile_threshold=95)
    if trigger is None:
        return []
    if price_change is not None and abs(price_change) >= 12 and (oi_percentile or 0) < 99:
        return []

    confirmations = [
        funding_pct is not None and funding_pct >= 90,
        depth_change is not None and depth_change <= -25,
        dex_liq_change is not None and dex_liq_change <= -20,
        volume_pct is not None and volume_pct < 50,
        venue_count is not None and venue_count <= 3,
    ]
    if severity == "low" and sum(confirmations) >= 2:
        severity = "medium"
    if severity == "medium" and sum(confirmations) >= 2:
        severity = "high"

    metrics = {
        "oi_change_1h": oi_change,
        "oi_percentile": oi_percentile,
        "oi_zscore": oi_zscore,
        "trigger": trigger,
        "oi_median_multiple_90d": oi_multiple,
        "price_change_1h": price_change,
        "funding_percentile_90d": funding_pct,
        "depth_change_1h": depth_change,
        "dex_liquidity_change_1h": dex_liq_change,
        "volume_change_percentile": volume_pct,
    }
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="aggregate_oi_1h",
            title=f"{symbol} | OI build-up | {severity.upper()}",
            message=(
                f"Open interest changed {oi_change:+.2f}% in 1h with trigger={trigger}. "
                f"Segmented/90d percentile is p{oi_percentile or 0:.0f}; EWMA z-score is "
                f"{oi_zscore or 0:.2f}; price moved {price_change or 0:+.2f}%."
            ),
            interpretation="Possible positioning build-up before volatility expansion.",
            metrics=metrics,
            venues={"scope": "aggregate"},
            dexscreener_url=metadata(features, "dex_liquidity_usd", "latest").get("dexscreener_url"),
        )
    ]
