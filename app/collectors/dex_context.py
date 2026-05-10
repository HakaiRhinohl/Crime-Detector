from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.dexscreener import DexScreenerClient
from app.db.models import AssetContract, AssetDataCoverage, DexSnapshot
from app.utils.time import floor_time

logger = logging.getLogger(__name__)


async def collect_dex_snapshots(session: AsyncSession) -> int:
    contracts = (
        await session.execute(select(AssetContract).where(AssetContract.is_active.is_(True)))
    ).scalars().all()
    by_chain: dict[str, list[AssetContract]] = {}
    for contract in contracts:
        by_chain.setdefault(contract.chain, []).append(contract)

    client = DexScreenerClient()
    ts = floor_time(seconds=60)
    inserted = 0
    try:
        for chain, rows in by_chain.items():
            for chunk_start in range(0, len(rows), 30):
                chunk = rows[chunk_start : chunk_start + 30]
                addresses = [row.token_address for row in chunk]
                pairs = await client.token_pairs(chain, addresses)
                pairs_by_token = _group_pairs_by_token(pairs)
                for contract in chunk:
                    pair = DexScreenerClient.select_main_pair(
                        pairs_by_token.get(contract.token_address.lower(), [])
                    )
                    if not pair:
                        continue
                    snap = DexScreenerClient.to_snapshot(pair)
                    stmt = (
                        insert(DexSnapshot)
                        .values(
                            ts=ts,
                            asset_id=contract.asset_id,
                            chain=snap.chain,
                            dex_id=snap.dex_id,
                            pair_address=snap.pair_address,
                            dexscreener_url=snap.dexscreener_url,
                            price_usd=snap.price_usd,
                            liquidity_usd=snap.liquidity_usd,
                            volume_5m_usd=snap.volume_5m_usd,
                            volume_1h_usd=snap.volume_1h_usd,
                            volume_6h_usd=snap.volume_6h_usd,
                            volume_24h_usd=snap.volume_24h_usd,
                            buys_1h=snap.buys_1h,
                            sells_1h=snap.sells_1h,
                            fdv=snap.fdv,
                            market_cap=snap.market_cap,
                            raw=snap.raw,
                        )
                        .on_conflict_do_nothing()
                    )
                    await session.execute(stmt)
                    coverage_stmt = (
                        insert(AssetDataCoverage)
                        .values(
                            asset_id=contract.asset_id,
                            has_dex=True,
                            dex_chains=[chain],
                        )
                        .on_conflict_do_update(
                            index_elements=[AssetDataCoverage.asset_id],
                            set_={"has_dex": True, "dex_chains": [chain]},
                        )
                    )
                    await session.execute(coverage_stmt)
                    inserted += 1
        await session.commit()
        return inserted
    finally:
        await client.close()


def _group_pairs_by_token(pairs: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for pair in pairs:
        base = (pair.get("baseToken") or {}).get("address")
        quote = (pair.get("quoteToken") or {}).get("address")
        for address in [base, quote]:
            if address:
                grouped.setdefault(address.lower(), []).append(pair)
    return grouped

