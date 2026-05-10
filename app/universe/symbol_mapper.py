from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.config.venues import COMMON_QUOTES, HYPERLIQUID, OKX, UPBIT


@dataclass(frozen=True)
class SymbolMapping:
    canonical_symbol: str
    base_asset: str
    quote_asset: str | None
    contract_multiplier: Decimal = Decimal("1")


def _strip_quote(raw: str) -> tuple[str, str | None]:
    for quote in COMMON_QUOTES:
        if raw.endswith(quote) and len(raw) > len(quote):
            return raw[: -len(quote)], quote
    return raw, None


def _apply_multiplier_prefix(base: str) -> tuple[str, Decimal]:
    match = re.match(r"^(1000|10000|100000|1000000)([A-Z0-9]+)$", base)
    if match:
        return match.group(2), Decimal(match.group(1))

    if len(base) > 1 and base[0] == "k" and base[1:].isalnum():
        return base[1:].upper(), Decimal("1000")

    if len(base) > 1 and base[0] == "K" and base[1:].isalnum():
        return base[1:].upper(), Decimal("1000")

    return base, Decimal("1")


def normalize_symbol(
    venue: str,
    raw_symbol: str,
    market_type: str,
    quote_asset: str | None = None,
    base_asset: str | None = None,
    overrides: dict[tuple[str, str], tuple[str, Decimal]] | None = None,
) -> SymbolMapping:
    overrides = overrides or {}
    override = overrides.get((venue, raw_symbol)) or overrides.get((venue, raw_symbol.upper()))
    if override:
        canonical, multiplier = override
        return SymbolMapping(
            canonical_symbol=canonical,
            base_asset=canonical,
            quote_asset=quote_asset,
            contract_multiplier=multiplier,
        )

    if base_asset:
        base = base_asset
        quote = quote_asset
    elif venue == OKX and "-" in raw_symbol:
        parts = raw_symbol.split("-")
        base = parts[0]
        quote = parts[1] if len(parts) > 1 else quote_asset
    elif venue == UPBIT and "-" in raw_symbol:
        quote, base = raw_symbol.split("-", 1)
    elif "/" in raw_symbol and venue == HYPERLIQUID:
        base, quote = raw_symbol.split("/", 1)
    else:
        base, quote = _strip_quote(raw_symbol)
        quote = quote_asset or quote

    canonical, multiplier = _apply_multiplier_prefix(base)
    return SymbolMapping(
        canonical_symbol=canonical,
        base_asset=base,
        quote_asset=quote,
        contract_multiplier=multiplier,
    )

