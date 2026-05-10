from __future__ import annotations

from app.anomalies.models import AlertCandidate, FeatureMap, metadata, value

DETECTOR = "dex_liquidity_compression"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    liq_change = value(features, "dex_liquidity_change", "1h")
    oi_pct = value(features, "oi_change_percentile", "90d_1h")
    price_pct = value(features, "price_change_percentile", "90d_1h")
    if liq_change is None or liq_change > -30:
        return []
    if (oi_pct or 0) < 95 and (price_pct or 0) < 95 and liq_change > -60:
        return []
    severity = "high" if liq_change <= -50 else "medium"
    return [
        AlertCandidate(
            asset_id=asset_id,
            detector=DETECTOR,
            severity=severity,
            event_key="dex_liquidity_1h",
            title=f"{symbol} | DEX liquidity compression | {severity.upper()}",
            message=f"DEX liquidity changed {liq_change:+.2f}% in 1h while another market signal is abnormal.",
            interpretation="On-chain liquidity is compressing while market activity is abnormal.",
            metrics={"dex_liquidity_change_1h": liq_change, "oi_percentile_90d": oi_pct, "price_percentile_90d": price_pct},
            venues={"scope": "dex"},
            dexscreener_url=metadata(features, "dex_liquidity_usd", "latest").get("dexscreener_url"),
        )
    ]

