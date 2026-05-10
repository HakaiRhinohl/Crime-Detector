from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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

