from __future__ import annotations

import struct
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import msgpack
import zstandard as zstd

from app.config.settings import get_settings
from app.utils.http import HTTPClient


@dataclass(frozen=True)
class Position:
    size: float
    notional_size: float
    funding_pnl: float
    entry_price: float
    leverage_type_flag: float
    leverage_multiplier: float
    liquidation_price: float
    account_value: float

    @property
    def side(self) -> str:
        return "long" if self.size > 0 else "short"


@dataclass(frozen=True)
class LiquidationCluster:
    market: str
    side: str
    price_bucket: float
    cluster_notional_usd: float
    positions_count: int


class HydromancerClient:
    def __init__(self, http: HTTPClient | None = None) -> None:
        settings = get_settings()
        headers = {"x-api-key": settings.hydromancer_api_key} if settings.hydromancer_api_key else None
        self.http = http or HTTPClient(settings.hydromancer_base_url, headers=headers)

    async def close(self) -> None:
        await self.http.close()

    async def snapshot_metadata(self) -> dict[str, Any]:
        return await self.http.post_json("/info", json={"type": "perpSnapshotTimestamp"})

    async def perp_snapshots(self, markets: list[str]) -> bytes:
        payload = {"type": "perpSnapshots", "market_names": markets or ["ALL"]}
        response = await self.http.client.post(
            "/info",
            json=payload,
            headers={"x-payload-format": "multi-zstd", "x-compression": "inner-zstd"},
        )
        response.raise_for_status()
        return response.content


def decompress_zstd(data: bytes) -> bytes:
    return zstd.ZstdDecompressor().decompress(data)


def decode_single_snapshot(data: bytes) -> dict[str, Any]:
    return msgpack.unpackb(decompress_zstd(data), raw=False)


def decode_multi_snapshot(data: bytes) -> list[dict[str, Any]]:
    if len(data) < 4:
        return []
    market_count = struct.unpack_from(">I", data, 0)[0]
    offset = 4
    snapshots: list[dict[str, Any]] = []
    for _ in range(market_count):
        if offset + 4 > len(data):
            break
        length = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        chunk = data[offset : offset + length]
        offset += length
        snapshots.append(decode_single_snapshot(chunk))
    return snapshots


def parse_positions(snapshot: dict[str, Any]) -> list[Position]:
    positions: list[Position] = []
    for row in snapshot.get("p", []) or []:
        if not isinstance(row, list | tuple) or len(row) < 8:
            continue
        positions.append(
            Position(
                size=float(row[0]),
                notional_size=abs(float(row[1])),
                funding_pnl=float(row[2]),
                entry_price=float(row[3]),
                leverage_type_flag=float(row[4]),
                leverage_multiplier=float(row[5]),
                liquidation_price=float(row[6]),
                account_value=float(row[7]),
            )
        )
    return positions


def liquidation_bucket(price: float, bucket_bps: Decimal = Decimal("25")) -> float:
    if price <= 0:
        return 0.0
    pct = float(bucket_bps) / 10_000.0
    bucket_size = price * pct
    return round(round(price / bucket_size) * bucket_size, 12)


def build_clusters(snapshot: dict[str, Any], bucket_bps: Decimal = Decimal("25")) -> list[LiquidationCluster]:
    market = snapshot.get("m") or snapshot.get("market")
    buckets: dict[tuple[str, float], tuple[float, int]] = {}
    for position in parse_positions(snapshot):
        if position.liquidation_price <= 0 or position.notional_size <= 0:
            continue
        bucket = liquidation_bucket(position.liquidation_price, bucket_bps=bucket_bps)
        key = (position.side, bucket)
        notional, count = buckets.get(key, (0.0, 0))
        buckets[key] = (notional + position.notional_size, count + 1)
    return [
        LiquidationCluster(
            market=market,
            side=side,
            price_bucket=bucket,
            cluster_notional_usd=notional,
            positions_count=count,
        )
        for (side, bucket), (notional, count) in buckets.items()
        if market
    ]

