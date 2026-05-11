from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config.thresholds import ZSCORE_THRESHOLDS


@dataclass(frozen=True)
class AlertCandidate:
    asset_id: int
    detector: str
    severity: str
    event_key: str
    title: str
    message: str
    interpretation: str
    metrics: dict[str, Any] = field(default_factory=dict)
    venues: dict[str, Any] = field(default_factory=dict)
    dexscreener_url: str | None = None


FeatureMap = dict[tuple[str, str], tuple[float | None, dict[str, Any]]]


def value(features: FeatureMap, name: str, window: str) -> float | None:
    return features.get((name, window), (None, {}))[0]


def metadata(features: FeatureMap, name: str, window: str) -> dict[str, Any]:
    return features.get((name, window), (None, {}))[1] or {}


def severity_from_percentile(percentile: float | None) -> str:
    if percentile is None:
        return "low"
    if percentile >= 99:
        return "critical"
    if percentile >= 97:
        return "high"
    if percentile >= 95:
        return "medium"
    return "low"


def severity_from_zscore(zscore: float | None) -> str:
    if zscore is None:
        return "low"
    absolute = abs(zscore)
    if absolute >= ZSCORE_THRESHOLDS["critical"]:
        return "critical"
    if absolute >= ZSCORE_THRESHOLDS["high"]:
        return "high"
    if absolute >= ZSCORE_THRESHOLDS["medium"]:
        return "medium"
    return "low"


SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def max_severity(*severities: str) -> str:
    return max(severities or ("low",), key=lambda item: SEVERITY_ORDER.get(item, 0))


def downgrade_severity(severity: str) -> str:
    ordered = ["low", "medium", "high", "critical"]
    idx = max(0, ordered.index(severity) - 1) if severity in ordered else 0
    return ordered[idx]


def preferred_value(features: FeatureMap, name: str, preferred_window: str, fallback_window: str) -> float | None:
    preferred = value(features, name, preferred_window)
    return preferred if preferred is not None else value(features, name, fallback_window)


def either_gate_trigger(
    percentile: float | None,
    zscore: float | None,
    *,
    percentile_threshold: float = 95.0,
    zscore_threshold: float | None = None,
) -> tuple[str | None, str]:
    z_threshold = zscore_threshold if zscore_threshold is not None else ZSCORE_THRESHOLDS["medium"]
    percentile_fired = percentile is not None and percentile >= percentile_threshold
    zscore_fired = zscore is not None and abs(zscore) >= z_threshold
    if percentile_fired and zscore_fired:
        return "both", max_severity(severity_from_percentile(percentile), severity_from_zscore(zscore))
    if percentile_fired:
        return "percentile_only", downgrade_severity(severity_from_percentile(percentile))
    if zscore_fired:
        return "zscore_only", downgrade_severity(severity_from_zscore(zscore))
    return None, "low"
