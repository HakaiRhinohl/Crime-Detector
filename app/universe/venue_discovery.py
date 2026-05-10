from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class VenueSymbolCandidate:
    venue: str
    market_type: str
    symbol: str
    base_asset: str | None
    quote_asset: str | None
    canonical_symbol: str
    contract_multiplier: Decimal = Decimal("1")
    metadata: dict[str, Any] = field(default_factory=dict)

