from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MarketSnapshotRow:
    ts: datetime
    asset_id: int
    venue: str
    market_type: str
    symbol: str
    price: float | None = None
    volume_24h_usd: float | None = None
    volume_1m_usd: float | None = None
    volume_5m_usd: float | None = None
    open_interest_usd: float | None = None
    funding_rate: float | None = None
    mark_price: float | None = None
    index_price: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawOrderbook:
    venue: str
    market_type: str
    symbol: str
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
    raw: dict[str, Any] = field(default_factory=dict)

