from __future__ import annotations

from datetime import UTC, datetime

from app.features.ewma import ewma_zscore
from app.features.percentiles import directional_median_multiple
from app.features.segmentation import bucket_btc_regime, get_segment


def test_btc_regime_bucket_and_segment() -> None:
    assert bucket_btc_regime(-0.08) == "strong_down"
    assert bucket_btc_regime(-0.03) == "down"
    assert bucket_btc_regime(0.0) == "flat"
    assert bucket_btc_regime(0.03) == "up"
    assert bucket_btc_regime(0.08) == "strong_up"
    assert get_segment(datetime(2026, 5, 11, 14, tzinfo=UTC), "flat") == (3, "weekday", "flat")
    assert get_segment(datetime(2026, 5, 10, 22, tzinfo=UTC), "up") == (5, "weekend", "up")


def test_ewma_zscore_and_directional_multiple() -> None:
    history = [1.0 + (idx % 3) * 0.1 for idx in range(100)]
    assert ewma_zscore(3.0, history, span=20) is not None
    assert directional_median_multiple(4.0, [-10.0, -8.0, 1.0, 2.0]) == 4.0 / 1.5
    assert directional_median_multiple(-4.0, [-10.0, -8.0, 1.0, 2.0]) == 4.0 / 9.0
