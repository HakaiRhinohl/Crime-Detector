from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.hydromancer_liquidations import (
    HydromancerClient,
    build_clusters,
    decode_multi_snapshot,
)
from app.db.models import AssetDataCoverage, HLLiquidationCluster, VenueSymbol
from app.utils.time import floor_time

logger = logging.getLogger(__name__)


async def collect_hl_liquidation_clusters(session: AsyncSession) -> int:
    hl_symbols = (
        await session.execute(select(VenueSymbol).where(VenueSymbol.venue == "hyperliquid"))
    ).scalars().all()
    if not hl_symbols:
        return 0

    asset_by_market = {row.symbol: row.asset_id for row in hl_symbols}
    client = HydromancerClient()
    ts = floor_time(seconds=60)
    inserted = 0
    try:
        payload = await client.perp_snapshots(list(asset_by_market))
        for snapshot in decode_multi_snapshot(payload):
            market = snapshot.get("m") or snapshot.get("market")
            asset_id = asset_by_market.get(market)
            if not asset_id:
                continue
            for cluster in build_clusters(snapshot):
                stmt = (
                    insert(HLLiquidationCluster)
                    .values(
                        ts=ts,
                        asset_id=asset_id,
                        market=cluster.market,
                        side=cluster.side,
                        price_bucket=cluster.price_bucket,
                        cluster_notional_usd=cluster.cluster_notional_usd,
                        positions_count=cluster.positions_count,
                        raw=snapshot,
                    )
                    .on_conflict_do_nothing()
                )
                await session.execute(stmt)
                coverage_stmt = (
                    insert(AssetDataCoverage)
                    .values(asset_id=asset_id, has_hl_liquidations=True)
                    .on_conflict_do_update(
                        index_elements=[AssetDataCoverage.asset_id],
                        set_={"has_hl_liquidations": True},
                    )
                )
                await session.execute(coverage_stmt)
                inserted += 1
        await session.commit()
        return inserted
    except Exception:
        logger.exception("Hydromancer liquidation collection failed")
        await session.rollback()
        return 0
    finally:
        await client.close()

