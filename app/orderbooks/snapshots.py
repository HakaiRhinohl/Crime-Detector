from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.binance import BinanceClient
from app.collectors.bybit import BybitClient
from app.collectors.hyperliquid import HyperliquidClient
from app.collectors.okx import OKXClient
from app.collectors.upbit import UpbitClient
from app.config.venues import BINANCE, BYBIT, HYPERLIQUID, OKX, UPBIT
from app.db.models import OrderbookSnapshot, VenueSymbol
from app.orderbooks.depth_calculator import calculate_depth
from app.utils.time import floor_time

logger = logging.getLogger(__name__)


async def collect_orderbook_snapshots(session: AsyncSession) -> int:
    rows = (
        await session.execute(select(VenueSymbol).where(VenueSymbol.is_active.is_(True)).limit(2000))
    ).scalars().all()
    clients = {
        BINANCE: BinanceClient.create(),
        BYBIT: BybitClient.create(),
        OKX: OKXClient.create(),
        HYPERLIQUID: HyperliquidClient.create(),
        UPBIT: UpbitClient.create(),
    }
    ts = floor_time(seconds=60)
    inserted = 0
    try:
        for symbol in rows:
            client = clients.get(symbol.venue)
            if client is None:
                continue
            try:
                book = await client.orderbook(symbol.symbol, symbol.market_type)
                depth = calculate_depth(book.bids, book.asks)
                if depth is None:
                    continue
                top_levels = {"bids": book.bids[:10], "asks": book.asks[:10], "raw": book.raw}
                stmt = (
                    insert(OrderbookSnapshot)
                    .values(
                        ts=ts,
                        asset_id=symbol.asset_id,
                        venue=symbol.venue,
                        market_type=symbol.market_type,
                        symbol=symbol.symbol,
                        mid_price=depth.mid_price,
                        spread_bps=depth.spread_bps,
                        bid_depth_50bps_usd=depth.bid_depth_50bps_usd,
                        ask_depth_50bps_usd=depth.ask_depth_50bps_usd,
                        bid_depth_100bps_usd=depth.bid_depth_100bps_usd,
                        ask_depth_100bps_usd=depth.ask_depth_100bps_usd,
                        bid_depth_200bps_usd=depth.bid_depth_200bps_usd,
                        ask_depth_200bps_usd=depth.ask_depth_200bps_usd,
                        imbalance_100bps=depth.imbalance_100bps,
                        raw_top_levels=top_levels,
                    )
                    .on_conflict_do_nothing()
                )
                await session.execute(stmt)
                inserted += 1
            except Exception:
                logger.exception(
                    "Orderbook snapshot failed",
                    extra={"venue": symbol.venue, "symbol": symbol.symbol},
                )
        await session.commit()
        return inserted
    finally:
        for client in clients.values():
            await client.close()

