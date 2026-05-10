from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.utils.http import HTTPClient, compact_raw, to_float


@dataclass(frozen=True)
class DexPairSnapshot:
    chain: str
    dex_id: str | None
    pair_address: str
    dexscreener_url: str | None
    price_usd: float | None
    liquidity_usd: float | None
    volume_5m_usd: float | None
    volume_1h_usd: float | None
    volume_6h_usd: float | None
    volume_24h_usd: float | None
    buys_1h: int | None
    sells_1h: int | None
    fdv: float | None
    market_cap: float | None
    raw: dict[str, Any]


class DexScreenerClient:
    def __init__(self, http: HTTPClient | None = None) -> None:
        self.http = http or HTTPClient("https://api.dexscreener.com")

    async def close(self) -> None:
        await self.http.close()

    async def token_pairs(self, chain: str, token_addresses: list[str]) -> list[dict[str, Any]]:
        if not token_addresses:
            return []
        joined = ",".join(token_addresses[:30])
        payload = await self.http.get_json(f"/tokens/v1/{chain}/{joined}")
        return payload if isinstance(payload, list) else []

    @staticmethod
    def select_main_pair(pairs: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not pairs:
            return None
        return max(pairs, key=lambda row: to_float((row.get("liquidity") or {}).get("usd")) or 0)

    @staticmethod
    def to_snapshot(pair: dict[str, Any]) -> DexPairSnapshot:
        volume = pair.get("volume") or {}
        txns = pair.get("txns") or {}
        txns_h1 = txns.get("h1") or {}
        liquidity = pair.get("liquidity") or {}
        return DexPairSnapshot(
            chain=pair.get("chainId") or "",
            dex_id=pair.get("dexId"),
            pair_address=pair.get("pairAddress") or "",
            dexscreener_url=pair.get("url"),
            price_usd=to_float(pair.get("priceUsd")),
            liquidity_usd=to_float(liquidity.get("usd")),
            volume_5m_usd=to_float(volume.get("m5")),
            volume_1h_usd=to_float(volume.get("h1")),
            volume_6h_usd=to_float(volume.get("h6")),
            volume_24h_usd=to_float(volume.get("h24")),
            buys_1h=txns_h1.get("buys"),
            sells_1h=txns_h1.get("sells"),
            fdv=to_float(pair.get("fdv")),
            market_cap=to_float(pair.get("marketCap")),
            raw=compact_raw(pair),
        )

