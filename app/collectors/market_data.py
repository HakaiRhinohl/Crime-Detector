from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors import binance as binance_module
from app.collectors import bybit as bybit_module
from app.collectors import okx as okx_module
from app.collectors.binance import BinanceClient
from app.collectors.bybit import BybitClient
from app.collectors.hyperliquid import HyperliquidClient, context_snapshot_values
from app.collectors.okx import OKXClient
from app.collectors.upbit import UpbitClient
from app.collectors.upbit import quote_volume_usd as upbit_quote_volume_usd
from app.config.venues import BINANCE, BYBIT, HYPERLIQUID, OKX, PERP, SPOT, UPBIT
from app.db.models import MarketSnapshot, VenueSymbol
from app.utils.http import compact_raw, to_float
from app.utils.time import floor_time

logger = logging.getLogger(__name__)
COMMIT_EVERY_ROWS = 50


async def collect_market_snapshots(session: AsyncSession) -> int:
    symbols = (
        await session.execute(
            select(VenueSymbol)
            .where(VenueSymbol.is_active.is_(True))
            .order_by(VenueSymbol.venue, VenueSymbol.market_type, VenueSymbol.symbol)
        )
    ).scalars().all()
    by_venue: dict[str, list[VenueSymbol]] = {}
    for symbol in symbols:
        by_venue.setdefault(symbol.venue, []).append(symbol)

    inserted = 0
    ts = floor_time(seconds=60)
    for venue, collector in [
        (BINANCE, _collect_binance),
        (BYBIT, _collect_bybit),
        (OKX, _collect_okx),
        (HYPERLIQUID, _collect_hyperliquid),
        (UPBIT, _collect_upbit),
    ]:
        venue_symbols = by_venue.get(venue, [])
        venue_inserted = await collector(session, ts, venue_symbols)
        logger.info(
            "Market data venue complete",
            extra={"venue": venue, "eligible_symbols": len(venue_symbols), "inserted": venue_inserted},
        )
        inserted += venue_inserted
    await session.commit()
    return inserted


async def _insert_snapshot(session: AsyncSession, values: dict) -> None:
    stmt = insert(MarketSnapshot).values(**values).on_conflict_do_nothing()
    await session.execute(stmt)


async def _collect_binance(session: AsyncSession, ts, symbols: list[VenueSymbol]) -> int:
    if not symbols:
        return 0
    client = BinanceClient.create()
    count = 0
    try:
        spot_tickers = await client.spot_tickers()
        futures_tickers = await client.futures_tickers()
        for symbol in symbols:
            row = (spot_tickers if symbol.market_type == SPOT else futures_tickers).get(symbol.symbol)
            if not row:
                continue
            price = to_float(row.get("lastPrice"))
            oi = funding = None
            if symbol.market_type == PERP:
                oi = await client.open_interest_usd(symbol.symbol, price)
                funding = await client.latest_funding(symbol.symbol)
            await _insert_snapshot(
                session,
                dict(
                    ts=ts,
                    asset_id=symbol.asset_id,
                    venue=BINANCE,
                    market_type=symbol.market_type,
                    symbol=symbol.symbol,
                    price=price,
                    volume_24h_usd=binance_module.quote_volume_usd(row, symbol.quote_asset),
                    open_interest_usd=oi,
                    funding_rate=funding,
                    raw=compact_raw(row),
                ),
            )
            count += 1
            if count % COMMIT_EVERY_ROWS == 0:
                await session.commit()
        return count
    finally:
        await client.close()


async def _collect_bybit(session: AsyncSession, ts, symbols: list[VenueSymbol]) -> int:
    if not symbols:
        return 0
    client = BybitClient.create()
    count = 0
    try:
        spot_tickers = await client.tickers(SPOT)
        perp_tickers = await client.tickers(PERP)
        for symbol in symbols:
            row = (spot_tickers if symbol.market_type == SPOT else perp_tickers).get(symbol.symbol)
            if not row:
                continue
            price = to_float(row.get("lastPrice"))
            oi = funding = None
            if symbol.market_type == PERP:
                oi = await client.open_interest_usd(symbol.symbol, price)
                funding = await client.latest_funding(symbol.symbol)
            await _insert_snapshot(
                session,
                dict(
                    ts=ts,
                    asset_id=symbol.asset_id,
                    venue=BYBIT,
                    market_type=symbol.market_type,
                    symbol=symbol.symbol,
                    price=price,
                    volume_24h_usd=bybit_module.quote_volume_usd(row, symbol.quote_asset),
                    open_interest_usd=oi,
                    funding_rate=funding,
                    raw=compact_raw(row),
                ),
            )
            count += 1
            if count % COMMIT_EVERY_ROWS == 0:
                await session.commit()
        return count
    finally:
        await client.close()


async def _collect_okx(session: AsyncSession, ts, symbols: list[VenueSymbol]) -> int:
    if not symbols:
        return 0
    client = OKXClient.create()
    count = 0
    try:
        spot_tickers = await client.tickers(SPOT)
        perp_tickers = await client.tickers(PERP)
        for symbol in symbols:
            row = (spot_tickers if symbol.market_type == SPOT else perp_tickers).get(symbol.symbol)
            if not row:
                continue
            price = to_float(row.get("last"))
            oi = funding = None
            if symbol.market_type == PERP:
                oi = await client.open_interest_usd(symbol.symbol, price)
                funding = await client.latest_funding(symbol.symbol)
            await _insert_snapshot(
                session,
                dict(
                    ts=ts,
                    asset_id=symbol.asset_id,
                    venue=OKX,
                    market_type=symbol.market_type,
                    symbol=symbol.symbol,
                    price=price,
                    volume_24h_usd=okx_module.quote_volume_usd(row, symbol.quote_asset),
                    open_interest_usd=oi,
                    funding_rate=funding,
                    raw=compact_raw(row),
                ),
            )
            count += 1
            if count % COMMIT_EVERY_ROWS == 0:
                await session.commit()
        return count
    finally:
        await client.close()


async def _collect_hyperliquid(session: AsyncSession, ts, symbols: list[VenueSymbol]) -> int:
    if not symbols:
        return 0
    client = HyperliquidClient.create()
    count = 0
    try:
        contexts = await client.market_contexts()
        for symbol in symbols:
            ctx = contexts.get(symbol.symbol)
            if not ctx:
                continue
            values = context_snapshot_values(ctx)
            await _insert_snapshot(
                session,
                dict(
                    ts=ts,
                    asset_id=symbol.asset_id,
                    venue=HYPERLIQUID,
                    market_type=PERP,
                    symbol=symbol.symbol,
                    price=values["price"],
                    volume_24h_usd=values["volume_24h_usd"],
                    open_interest_usd=values["open_interest_usd"],
                    funding_rate=values["funding_rate"],
                    mark_price=values["mark_price"],
                    raw=compact_raw(ctx),
                ),
            )
            count += 1
            if count % COMMIT_EVERY_ROWS == 0:
                await session.commit()
        return count
    finally:
        await client.close()


async def _collect_upbit(session: AsyncSession, ts, symbols: list[VenueSymbol]) -> int:
    if not symbols:
        return 0
    client = UpbitClient.create()
    count = 0
    try:
        conversion_tickers = await client.tickers(["KRW-USDT", "KRW-BTC"])
        krw_per_usdt = to_float((conversion_tickers.get("KRW-USDT") or {}).get("trade_price"))
        btc_krw = to_float((conversion_tickers.get("KRW-BTC") or {}).get("trade_price"))
        btc_usd = btc_krw / krw_per_usdt if btc_krw and krw_per_usdt else None
        for chunk_start in range(0, len(symbols), 100):
            chunk = symbols[chunk_start : chunk_start + 100]
            tickers = await client.tickers([row.symbol for row in chunk])
            for symbol in chunk:
                row = tickers.get(symbol.symbol)
                if not row:
                    continue
                await _insert_snapshot(
                    session,
                    dict(
                        ts=ts,
                        asset_id=symbol.asset_id,
                        venue=UPBIT,
                        market_type=SPOT,
                        symbol=symbol.symbol,
                        price=to_float(row.get("trade_price")),
                        volume_24h_usd=upbit_quote_volume_usd(row, krw_per_usdt=krw_per_usdt, btc_usd=btc_usd),
                        raw=compact_raw(row),
                    ),
                )
                count += 1
                if count % COMMIT_EVERY_ROWS == 0:
                    await session.commit()
        return count
    finally:
        await client.close()
