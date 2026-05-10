from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.collectors.base import RawOrderbook
from app.config.venues import BYBIT, PERP, SPOT, USD_QUOTES
from app.universe.symbol_mapper import normalize_symbol
from app.universe.venue_discovery import VenueSymbolCandidate
from app.utils.http import HTTPClient, compact_raw, to_float


@dataclass
class BybitClient:
    http: HTTPClient

    @classmethod
    def create(cls) -> BybitClient:
        return cls(HTTPClient("https://api.bybit.com"))

    async def close(self) -> None:
        await self.http.close()

    async def _paged_instruments(self, category: str) -> list[dict[str, Any]]:
        cursor: str | None = None
        items: list[dict[str, Any]] = []
        while True:
            params = {"category": category, "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            payload = await self.http.get_json("/v5/market/instruments-info", params=params)
            result = payload.get("result", {})
            items.extend(result.get("list", []))
            cursor = result.get("nextPageCursor")
            if not cursor:
                return items

    async def discover_symbols(self) -> list[VenueSymbolCandidate]:
        candidates: list[VenueSymbolCandidate] = []
        for category, market_type in [("spot", SPOT), ("linear", PERP)]:
            for item in await self._paged_instruments(category):
                if item.get("status") not in {"Trading", "TRADING"}:
                    continue
                mapping = normalize_symbol(
                    BYBIT,
                    item["symbol"],
                    market_type,
                    quote_asset=item.get("quoteCoin"),
                    base_asset=item.get("baseCoin"),
                )
                candidates.append(
                    VenueSymbolCandidate(
                        venue=BYBIT,
                        market_type=market_type,
                        symbol=item["symbol"],
                        base_asset=mapping.base_asset,
                        quote_asset=mapping.quote_asset,
                        canonical_symbol=mapping.canonical_symbol,
                        contract_multiplier=mapping.contract_multiplier,
                        metadata=compact_raw(item),
                    )
                )
        return candidates

    async def tickers(self, market_type: str) -> dict[str, dict[str, Any]]:
        category = "spot" if market_type == SPOT else "linear"
        payload = await self.http.get_json("/v5/market/tickers", params={"category": category})
        return {row["symbol"]: row for row in payload.get("result", {}).get("list", [])}

    async def open_interest_usd(self, symbol: str, mark_price: float | None = None) -> float | None:
        payload = await self.http.get_json(
            "/v5/market/open-interest",
            params={"category": "linear", "symbol": symbol, "intervalTime": "5min", "limit": 1},
        )
        rows = payload.get("result", {}).get("list", [])
        if not rows:
            return None
        oi = to_float(rows[0].get("openInterest"))
        if oi is None:
            return None
        return oi * mark_price if mark_price is not None else oi

    async def latest_funding(self, symbol: str) -> float | None:
        payload = await self.http.get_json(
            "/v5/market/funding/history",
            params={"category": "linear", "symbol": symbol, "limit": 1},
        )
        rows = payload.get("result", {}).get("list", [])
        if not rows:
            return None
        return to_float(rows[0].get("fundingRate"))

    async def orderbook(self, symbol: str, market_type: str, limit: int = 200) -> RawOrderbook:
        category = "spot" if market_type == SPOT else "linear"
        raw = await self.http.get_json(
            "/v5/market/orderbook",
            params={"category": category, "symbol": symbol, "limit": min(limit, 500)},
        )
        result = raw.get("result", {})
        return RawOrderbook(
            venue=BYBIT,
            market_type=market_type,
            symbol=symbol,
            bids=[(float(price), float(size)) for price, size in result.get("b", [])],
            asks=[(float(price), float(size)) for price, size in result.get("a", [])],
            raw=compact_raw(result),
        )


def quote_volume_usd(row: dict[str, Any], quote_asset: str | None) -> float | None:
    value = row.get("turnover24h") or row.get("volume24h")
    volume = to_float(value)
    if quote_asset in USD_QUOTES:
        return volume
    return None

