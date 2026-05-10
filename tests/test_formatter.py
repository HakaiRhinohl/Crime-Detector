from __future__ import annotations

from app.alerts.formatter import format_telegram_alert
from app.anomalies.models import AlertCandidate


def test_telegram_format_includes_where_to_trade_and_interpretation() -> None:
    candidate = AlertCandidate(
        asset_id=1,
        detector="oi_build_up",
        severity="high",
        event_key="x",
        title="WIF | OI build-up | HIGH",
        message="Bybit OI increased +38% in 1h.",
        interpretation="Possible positioning build-up before volatility expansion.",
        metrics={"oi_change_1h": 38.0},
        venues={"primary": "bybit"},
        dexscreener_url="https://dexscreener.com/solana/x",
    )
    text = format_telegram_alert(candidate, "WIF", ["Binance", "OKX"], ["Bybit"])
    assert "Where to trade" in text
    assert "Spot: Binance, OKX" in text
    assert "Perp: Bybit" in text
    assert "https://dexscreener.com/solana/x" in text
    assert "Possible positioning" in text

