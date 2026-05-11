from __future__ import annotations

from app.anomalies.oi_build_up import detect as detect_oi_build_up
from app.anomalies.venue_specific import detect as detect_venue_specific


def test_oi_build_up_requires_percentile_and_median_multiple() -> None:
    features = {
        ("oi_change", "1h"): (38.0, {}),
        ("oi_change_percentile", "90d_1h"): (97.0, {}),
        ("oi_change_median_multiple", "90d_1h"): (2.5, {}),
        ("price_change", "1h"): (2.4, {}),
        ("funding_percentile", "90d"): (91.0, {}),
        ("depth_100bps_change", "1h"): (-31.0, {}),
        ("dex_liquidity_usd", "latest"): (1000000.0, {"dexscreener_url": "https://dexscreener.com/solana/x"}),
    }
    candidates = detect_oi_build_up(1, "WIF", features)
    assert len(candidates) == 1
    assert candidates[0].severity == "high"
    assert candidates[0].dexscreener_url == "https://dexscreener.com/solana/x"


def test_venue_specific_detects_dominant_venue_share() -> None:
    features = {
        ("venue_oi_share", "latest"): (0.82, {"venue": "bybit", "market_type": "perp"}),
        ("oi_change_percentile", "seg_60d_1h"): (96.0, {}),
    }
    candidates = detect_venue_specific(1, "WIF", features)
    assert candidates
    assert candidates[0].venues["primary"] == "bybit"
