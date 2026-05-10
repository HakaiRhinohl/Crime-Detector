from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.collectors.base import RawOrderbook
from app.config.venues import BINANCE, PERP, SPOT, USD_QUOTES
from app.universe.symbol_mapper import normalize_symbol
from app.universe.venue_discovery import VenueSymbolCandidate
from app.utils.http import HTTPClient, compact_raw, to_float


@dataclass
class BinanceClient:
    spot: HTTPClient
    futures: HTTPClient

    @classmethod
    def create(cls) -> BinanceClient:
        return cls(
            spot=HTTPClient("https://api.binance.com"),
            futures=HTTPClient("https://fapi.binance.com"),
        )

    async def close(self) -> None:
        await self.spot.close()
        await self.futures.close()

    async def discover_symbols(self) -> list[VenueSymbolCandidate]:
        spot_info, futures_info = await self.spot.get_json("/api/v3/exchangeInfo"), await self.futures.get_json(
            "/fapi/v1/exchangeInfo"
        )
        candidates: list[VenueSymbolCandidate] = []
        for item in spot_info.get("symbols", []):
            if item.get("status") != "TRADING" or not item.get("isSpotTradingAllowed", True):
                continue
            mapping = normalize_symbol(
                BINANCE,
                item["symbol"],
                SPOT,
                quote_asset=item.get("quoteAsset"),
                base_asset=item.get("baseAsset"),
            )
            candidates.append(
                VenueSymbolCandidate(
                    venue=BINANCE,
                    market_type=SPOT,
                    symbol=item["symbol"],
                    base_asset=mapping.base_asset,
                    quote_asset=mapping.quote_asset,
                    canonical_symbol=mapping.canonical_symbol,
                    contract_multiplier=mapping.contract_multiplier,
                    metadata=compact_raw(item),
                )
            )

        for item in futures_info.get("symbols", []):
            if item.get("status") != "TRADING" or item.get("contractType") != "PERPETUAL":
                continue
            mapping = normalize_symbol(
                BINANCE,
                item["symbol"],
                PERP,
                quote_asset=item.get("quoteAsset"),
                base_asset=item.get("baseAsset"),
            )
            candidates.append(
                VenueSymbolCandidate(
                    venue=BINANCE,
                    market_type=PERP,
                    symbol=item["symbol"],
                    base_asset=mapping.base_asset,
                    quote_asset=mapping.quote_asset,
                    canonical_symbol=mapping.canonical_symbol,
                    contract_multiplier=mapping.contract_multiplier,
                    metadata=compact_raw(item),
                )
            )
        return candidates

    async def spot_tickers(self) -> dict[str, dict[str, Any]]:
        rows = await self.spot.get_json("/api/v3/ticker/24hr")
        return {row["symbol"]: row for row in rows}

    async def futures_tickers(self) -> dict[str, dict[str, Any]]:
        rows = await self.futures.get_json("/fapi/v1/ticker/24hr")
        return {row["symbol"]: row for row in rows}

    async def open_interest_usd(self, symbol: str, mark_price: float | None = None) -> float | None:
        row = await self.futures.get_json("/fapi/v1/openInterest", params={"symbol": symbol})
        open_interest = to_float(row.get("openInterest"))
        if open_interest is None:
            return None
        if mark_price is None:
            return open_interest
        return open_interest * mark_price

    async def latest_funding(self, symbol: str) -> float | None:
        rows = await self.futures.get_json("/fapi/v1/fundingRate", params={"symbol": symbol, "limit": 1})
        if not rows:
            return None
        return to_float(rows[-1].get("fundingRate"))

    async def orderbook(self, symbol: str, market_type: str, limit: int = 100) -> RawOrderbook:
        client = self.spot if market_type == SPOT else self.futures
        path = "/api/v3/depth" if market_type == SPOT else "/fapi/v1/depth"
        raw = await client.get_json(path, params={"symbol": symbol, "limit": limit})
        return RawOrderbook(
            venue=BINANCE,
            market_type=market_type,
            symbol=symbol,
            bids=[(float(price), float(size)) for price, size in raw.get("bids", [])],
            asks=[(float(price), float(size)) for price, size in raw.get("asks", [])],
            raw=compact_raw(raw),
        )


def quote_volume_usd(row: dict[str, Any], quote_asset: str | None) -> float | None:
    volume = to_float(row.get("quoteVolume"))
    if quote_asset in USD_QUOTES:
        return volume
    return None

