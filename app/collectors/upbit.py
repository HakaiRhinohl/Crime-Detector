from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.collectors.base import RawOrderbook
from app.config.settings import get_settings
from app.config.venues import SPOT, UPBIT
from app.universe.symbol_mapper import normalize_symbol
from app.universe.venue_discovery import VenueSymbolCandidate
from app.utils.http import HTTPClient, compact_raw, to_float


@dataclass
class UpbitClient:
    http: HTTPClient

    @classmethod
    def create(cls) -> UpbitClient:
        return cls(HTTPClient(get_settings().upbit_base_url))

    async def close(self) -> None:
        await self.http.close()

    async def discover_symbols(self) -> list[VenueSymbolCandidate]:
        rows = await self.http.get_json("/v1/market/all", params={"is_details": "true"})
        candidates: list[VenueSymbolCandidate] = []
        for row in rows:
            market = row["market"]
            mapping = normalize_symbol(UPBIT, market, SPOT)
            candidates.append(
                VenueSymbolCandidate(
                    venue=UPBIT,
                    market_type=SPOT,
                    symbol=market,
                    base_asset=mapping.base_asset,
                    quote_asset=mapping.quote_asset,
                    canonical_symbol=mapping.canonical_symbol,
                    contract_multiplier=mapping.contract_multiplier,
                    metadata=compact_raw(row),
                )
            )
        return candidates

    async def tickers(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        if not symbols:
            return {}
        payload = await self.http.get_json("/v1/ticker", params={"markets": ",".join(symbols[:200])})
        return {row["market"]: row for row in payload}

    async def orderbook(self, symbol: str, limit: int = 30) -> RawOrderbook:
        rows = await self.http.get_json("/v1/orderbook", params={"markets": symbol, "count": limit})
        book = rows[0] if rows else {}
        units = book.get("orderbook_units", [])
        return RawOrderbook(
            venue=UPBIT,
            market_type=SPOT,
            symbol=symbol,
            bids=[(float(row["bid_price"]), float(row["bid_size"])) for row in units],
            asks=[(float(row["ask_price"]), float(row["ask_size"])) for row in units],
            raw=compact_raw(book),
        )


def quote_volume_usd(
    row: dict[str, Any], krw_per_usdt: float | None = None, btc_usd: float | None = None
) -> float | None:
    quote = row.get("market", "").split("-", 1)[0]
    volume = to_float(row.get("acc_trade_price_24h"))
    if quote in {"USDT", "USDC", "USD"}:
        return volume
    if quote == "KRW" and volume is not None and krw_per_usdt:
        return volume / krw_per_usdt
    if quote == "BTC" and volume is not None and btc_usd:
        return volume * btc_usd
    return None
