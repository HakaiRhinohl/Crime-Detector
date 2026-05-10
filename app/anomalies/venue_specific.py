from __future__ import annotations

from app.anomalies.models import AlertCandidate, FeatureMap

DETECTOR = "venue_specific"


def detect(asset_id: int, symbol: str, features: FeatureMap) -> list[AlertCandidate]:
    candidates: list[AlertCandidate] = []
    for (name, _window), (metric_value, meta) in features.items():
        if name not in {"venue_oi_share", "venue_volume_share", "upbit_volume_share"}:
            continue
        if metric_value is None:
            continue
        if metric_value >= 0.75:
            venue = meta.get("venue", "unknown")
            severity = "critical" if metric_value >= 0.9 else "high"
            candidates.append(
                AlertCandidate(
                    asset_id=asset_id,
                    detector=DETECTOR,
                    severity=severity,
                    event_key=f"{name}:{venue}",
                    title=f"{symbol} | Venue-specific anomaly | {severity.upper()}",
                    message=f"{venue} accounts for {metric_value:.0%} of the latest {name.replace('_', ' ')}.",
                    interpretation="Anomaly is isolated to one venue, which can indicate early positioning or a temporary dislocation.",
                    metrics={name: metric_value},
                    venues={"primary": venue},
                )
            )
    return candidates
