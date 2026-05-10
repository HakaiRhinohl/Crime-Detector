from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.collectors.base import RawOrderbook
from app.config.venues import HYPERLIQUID, PERP
from app.universe.symbol_mapper import normalize_symbol
from app.universe.venue_discovery import VenueSymbolCandidate
from app.utils.http import HTTPClient, compact_raw, to_float


@dataclass
class HyperliquidClient:
    http: HTTPClient

    @classmethod
    def create(cls) -> HyperliquidClient:
        return cls(HTTPClient("https://api.hyperliquid.xyz"))

    async def close(self) -> None:
        await self.http.close()

    async def post_info(self, payload: dict[str, Any]) -> Any:
        return await self.http.post_json("/info", json=payload)

    async def meta_and_asset_contexts(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        result = await self.post_info({"type": "metaAndAssetCtxs"})
        if isinstance(result, list) and len(result) >= 2:
            return result[0], result[1]
        return {}, []

    async def discover_symbols(self) -> list[VenueSymbolCandidate]:
        meta, _contexts = await self.meta_and_asset_contexts()
        candidates: list[VenueSymbolCandidate] = []
        for item in meta.get("universe", []):
            if item.get("isDelisted"):
                continue
            raw_symbol = item["name"]
            mapping = normalize_symbol(HYPERLIQUID, raw_symbol, PERP)
            candidates.append(
                VenueSymbolCandidate(
                    venue=HYPERLIQUID,
                    market_type=PERP,
                    symbol=raw_symbol,
                    base_asset=mapping.base_asset,
                    quote_asset="USDC",
                    canonical_symbol=mapping.canonical_symbol,
                    contract_multiplier=mapping.contract_multiplier,
                    metadata=compact_raw(item),
                )
            )
        return candidates

    async def all_mids(self) -> dict[str, float]:
        payload = await self.post_info({"type": "allMids"})
        return {symbol: float(price) for symbol, price in payload.items()}

    async def market_contexts(self) -> dict[str, dict[str, Any]]:
        meta, contexts = await self.meta_and_asset_contexts()
        universe = meta.get("universe", [])
        out: dict[str, dict[str, Any]] = {}
        for item, ctx in zip(universe, contexts, strict=False):
            out[item["name"]] = ctx
        return out

    async def orderbook(self, symbol: str, limit: int = 20) -> RawOrderbook:
        raw = await self.post_info({"type": "l2Book", "coin": symbol})
        levels = raw.get("levels", [[], []])
        bids = levels[0] if levels else []
        asks = levels[1] if len(levels) > 1 else []
        return RawOrderbook(
            venue=HYPERLIQUID,
            market_type=PERP,
            symbol=symbol,
            bids=[(float(row["px"]), float(row["sz"])) for row in bids[:limit]],
            asks=[(float(row["px"]), float(row["sz"])) for row in asks[:limit]],
            raw=compact_raw(raw),
        )


def context_snapshot_values(ctx: dict[str, Any]) -> dict[str, float | None]:
    mark = to_float(ctx.get("markPx") or ctx.get("markPrice"))
    mid = to_float(ctx.get("midPx") or ctx.get("mid"))
    price = mid or mark
    open_interest = to_float(ctx.get("openInterest"))
    return {
        "price": price,
        "mark_price": mark,
        "open_interest_usd": open_interest * price if open_interest is not None and price else open_interest,
        "funding_rate": to_float(ctx.get("funding")),
        "volume_24h_usd": to_float(ctx.get("dayNtlVlm")),
    }

