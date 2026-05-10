from __future__ import annotations

from app.anomalies.models import AlertCandidate


def format_telegram_alert(
    candidate: AlertCandidate,
    symbol: str,
    spot_venues: list[str] | None = None,
    perp_venues: list[str] | None = None,
) -> str:
    spot = ", ".join(spot_venues or []) or "None"
    perp = ", ".join(perp_venues or []) or "None"
    dex = candidate.dexscreener_url or "Unavailable"
    metrics = _format_metrics(candidate.metrics)
    venue = _format_venues(candidate.venues)
    return (
        f"{symbol} | {candidate.detector.replace('_', ' ')} | {candidate.severity.upper()}\n\n"
        f"Event:\n{candidate.message}\n\n"
        f"Venue breakdown:\n{venue}\n\n"
        f"Where to trade:\n"
        f"Spot: {spot}\n"
        f"Perp: {perp}\n"
        f"DEX: {dex}\n\n"
        f"Key metrics:\n{metrics}\n\n"
        f"Interpretation:\n{candidate.interpretation}\n\n"
        f"Open:\nDEX Screener chart"
    )


def _format_metrics(metrics: dict) -> str:
    if not metrics:
        return "- No metrics"
    lines = []
    for key, value in metrics.items():
        if isinstance(value, float):
            lines.append(f"- {key}: {value:.4g}")
        else:
            lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _format_venues(venues: dict) -> str:
    if not venues:
        return "Aggregate"
    return ", ".join(f"{key}: {value}" for key, value in venues.items())

