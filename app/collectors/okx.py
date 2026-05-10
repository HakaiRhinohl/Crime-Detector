from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.collectors.base import RawOrderbook
from app.config.venues import OKX, PERP, SPOT, USD_QUOTES
from app.universe.symbol_mapper import normalize_symbol
from app.universe.venue_discovery import VenueSymbolCandidate
from app.utils.http import HTTPClient, compact_raw, to_float


@dataclass
class OKXClient:
    http: HTTPClient

    @classmethod
    def create(cls) -> OKXClient:
        return cls(HTTPClient("https://www.okx.com"))

    async def close(self) -> None:
        await self.http.close()

    async def discover_symbols(self) -> list[VenueSymbolCandidate]:
        candidates: list[VenueSymbolCandidate] = []
        for inst_type, market_type in [("SPOT", SPOT), ("SWAP", PERP)]:
            payload = await self.http.get_json("/api/v5/public/instruments", params={"instType": inst_type})
            for item in payload.get("data", []):
                if item.get("state") != "live":
                    continue
                mapping = normalize_symbol(
                    OKX,
                    item["instId"],
                    market_type,
                    quote_asset=item.get("quoteCcy") or item.get("settleCcy"),
                    base_asset=item.get("baseCcy") or item.get("uly", "").split("-")[0],
                )
                candidates.append(
                    VenueSymbolCandidate(
                        venue=OKX,
                        market_type=market_type,
                        symbol=item["instId"],
                        base_asset=mapping.base_asset,
                        quote_asset=mapping.quote_asset,
                        canonical_symbol=mapping.canonical_symbol,
                        contract_multiplier=mapping.contract_multiplier,
                        metadata=compact_raw(item),
                    )
                )
        return candidates

    async def tickers(self, market_type: str) -> dict[str, dict[str, Any]]:
        inst_type = "SPOT" if market_type == SPOT else "SWAP"
        payload = await self.http.get_json("/api/v5/market/tickers", params={"instType": inst_type})
        return {row["instId"]: row for row in payload.get("data", [])}

    async def open_interest_usd(self, inst_id: str, mark_price: float | None = None) -> float | None:
        payload = await self.http.get_json("/api/v5/public/open-interest", params={"instId": inst_id})
        rows = payload.get("data", [])
        if not rows:
            return None
        oi_usd = to_float(rows[0].get("oiUsd"))
        if oi_usd is not None:
            return oi_usd
        oi = to_float(rows[0].get("oi"))
        return oi * mark_price if oi is not None and mark_price is not None else oi

    async def latest_funding(self, inst_id: str) -> float | None:
        payload = await self.http.get_json("/api/v5/public/funding-rate", params={"instId": inst_id})
        rows = payload.get("data", [])
        if not rows:
            return None
        return to_float(rows[0].get("fundingRate"))

    async def orderbook(self, inst_id: str, market_type: str, limit: int = 100) -> RawOrderbook:
        raw = await self.http.get_json("/api/v5/market/books", params={"instId": inst_id, "sz": limit})
        rows = raw.get("data", [])
        book = rows[0] if rows else {}
        return RawOrderbook(
            venue=OKX,
            market_type=market_type,
            symbol=inst_id,
            bids=[(float(price), float(size)) for price, size, *_ in book.get("bids", [])],
            asks=[(float(price), float(size)) for price, size, *_ in book.get("asks", [])],
            raw=compact_raw(book),
        )


def quote_volume_usd(row: dict[str, Any], quote_asset: str | None) -> float | None:
    volume = to_float(row.get("volCcy24h") or row.get("vol24h"))
    if quote_asset in USD_QUOTES:
        return volume
    return None

