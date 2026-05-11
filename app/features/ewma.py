from __future__ import annotations

from math import sqrt


def ewma_zscore(
    current: float | None,
    history: list[float],
    span: int = 168,  # TUNABLE: 7 days of hourly observations
) -> float | None:
    """
    Compute z-score of current value against EWMA baseline.

    Uses exponentially weighted moving average and variance. span=168 is slow
    enough that sustained manipulation looks anomalous for its full duration,
    but fast enough to adapt to legitimate structural changes within about
    two weeks.
    """
    if current is None:
        return None
    clean = [value for value in history if value is not None]
    if len(clean) < span // 2:
        return None

    alpha = 2 / (span + 1)
    mean = clean[0]
    var = 0.0
    for value in clean[1:]:
        mean = alpha * value + (1 - alpha) * mean
        var = alpha * ((value - mean) ** 2) + (1 - alpha) * var

    if var <= 0:
        return None
    return (current - mean) / sqrt(var)

