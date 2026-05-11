from __future__ import annotations

from app.anomalies.depth_asymmetry_shift import detect as detect_depth_asymmetry
from app.anomalies.funding_oi_divergence import detect as detect_funding_divergence
from app.anomalies.silent_oi_build import detect as detect_silent_oi


def test_silent_oi_build_detects_quiet_positioning() -> None:
    candidates = detect_silent_oi(
        1,
        "WIF",
        {
            ("oi_change", "4h"): (18.0, {}),
            ("oi_change_percentile", "seg_60d_1h"): (92.0, {}),
            ("price_change", "4h"): (1.1, {}),
            ("volume_change_percentile", "seg_60d_1h"): (35.0, {}),
            ("supported_venue_count", "latest"): (2.0, {}),
        },
    )
    assert len(candidates) == 1
    assert candidates[0].severity == "high"


def test_depth_asymmetry_shift_detects_extreme_imbalance() -> None:
    candidates = detect_depth_asymmetry(
        1,
        "WIF",
        {
            ("depth_imbalance_100bps", "latest"): (-0.65, {}),
            ("depth_imbalance_percentile", "seg_60d"): (2.0, {}),
            ("oi_change_percentile", "seg_60d_1h"): (91.0, {}),
        },
    )
    assert len(candidates) == 1
    assert candidates[0].severity == "high"
    assert "Bid support" in candidates[0].interpretation


def test_funding_oi_divergence_detects_extreme_opposition() -> None:
    candidates = detect_funding_divergence(
        1,
        "WIF",
        {
            ("funding_oi_divergent", "latest"): (1.0, {}),
            ("oi_change_percentile", "seg_60d_1h"): (98.0, {}),
            ("funding_percentile", "90d"): (9.0, {}),
            ("oi_change", "1h"): (11.0, {}),
            ("funding_current", "latest"): (-0.01, {}),
        },
    )
    assert len(candidates) == 1
    assert candidates[0].severity == "high"
