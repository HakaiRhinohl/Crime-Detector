from __future__ import annotations

from statistics import median


def quantile(values: list[float], percentile: float) -> float | None:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    rank = (percentile / 100.0) * (len(clean) - 1)
    low = int(rank)
    high = min(low + 1, len(clean) - 1)
    weight = rank - low
    return clean[low] * (1 - weight) + clean[high] * weight


def percentile_rank(value: float | None, history: list[float]) -> float | None:
    if value is None:
        return None
    clean = sorted(v for v in history if v is not None)
    if not clean:
        return None
    below_or_equal = sum(1 for item in clean if item <= value)
    return (below_or_equal / len(clean)) * 100.0


def median_multiple(value: float | None, history: list[float]) -> float | None:
    if value is None:
        return None
    clean = [abs(v) for v in history if v is not None and v != 0]
    if not clean:
        return None
    med = median(clean)
    return abs(value) / med if med else None

