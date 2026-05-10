from __future__ import annotations

from app.features.percentiles import median_multiple, percentile_rank, quantile


def test_quantile_interpolates() -> None:
    assert quantile([1, 2, 3, 4], 50) == 2.5


def test_percentile_rank() -> None:
    assert percentile_rank(3, [1, 2, 3, 4]) == 75.0


def test_median_multiple() -> None:
    assert median_multiple(10, [1, 2, 3, 4]) == 4.0

