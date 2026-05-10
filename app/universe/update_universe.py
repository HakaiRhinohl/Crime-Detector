from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.binance import BinanceClient
from app.collectors.bybit import BybitClient
from app.collectors.hyperliquid import HyperliquidClient
from app.collectors.okx import OKXClient
from app.collectors.upbit import UpbitClient
from app.db.models import Asset, AssetDataCoverage, ExcludedAsset, SymbolOverride, VenueSymbol
from app.universe.symbol_mapper import normalize_symbol
from app.universe.venue_discovery import VenueSymbolCandidate

logger = logging.getLogger(__name__)


async def load_overrides(session: AsyncSession) -> dict[tuple[str, str], tuple[str, Decimal]]:
    rows = (await session.execute(select(SymbolOverride))).scalars().all()
    return {
        (row.venue, row.raw_symbol): (row.canonical_symbol, Decimal(str(row.contract_multiplier)))
        for row in rows
    }


async def discover_all_venues() -> list[VenueSymbolCandidate]:
    clients = [
        BinanceClient.create(),
        BybitClient.create(),
        OKXClient.create(),
        HyperliquidClient.create(),
        UpbitClient.create(),
    ]
    candidates: list[VenueSymbolCandidate] = []
    try:
        for client in clients:
            try:
                candidates.extend(await client.discover_symbols())
            except Exception:
                logger.exception("Venue discovery failed", extra={"client": client.__class__.__name__})
    finally:
        for client in clients:
            await client.close()
    return candidates


async def upsert_universe(session: AsyncSession, candidates: list[VenueSymbolCandidate]) -> int:
    excluded = {
        row[0].upper()
        for row in (await session.execute(select(ExcludedAsset.symbol))).all()
    }
    overrides = await load_overrides(session)
    changed = 0
    asset_ids_by_symbol: dict[str, int] = {}

    for candidate in candidates:
        mapping = normalize_symbol(
            candidate.venue,
            candidate.symbol,
            candidate.market_type,
            quote_asset=candidate.quote_asset,
            base_asset=candidate.base_asset,
            overrides=overrides,
        )
        canonical = mapping.canonical_symbol
        if canonical.upper() in excluded:
            continue

        if canonical not in asset_ids_by_symbol:
            asset_stmt = (
                insert(Asset)
                .values(symbol=canonical, is_active=True)
                .on_conflict_do_update(
                    index_elements=[Asset.symbol],
                    set_={"is_active": True},
                )
                .returning(Asset.id)
            )
            asset_id = (await session.execute(asset_stmt)).scalar_one()
            asset_ids_by_symbol[canonical] = asset_id
        else:
            asset_id = asset_ids_by_symbol[canonical]

        venue_stmt = (
            insert(VenueSymbol)
            .values(
                asset_id=asset_id,
                venue=candidate.venue,
                market_type=candidate.market_type,
                symbol=candidate.symbol,
                quote_asset=mapping.quote_asset,
                base_asset=mapping.base_asset,
                contract_multiplier=mapping.contract_multiplier,
                is_active=True,
                metadata_=candidate.metadata,
            )
            .on_conflict_do_update(
                constraint="uq_venue_symbol",
                set_={
                    "asset_id": asset_id,
                    "quote_asset": mapping.quote_asset,
                    "base_asset": mapping.base_asset,
                    "contract_multiplier": mapping.contract_multiplier,
                    "is_active": True,
                    "metadata": candidate.metadata,
                },
            )
        )
        await session.execute(venue_stmt)
        changed += 1

    await refresh_coverage(session)
    await session.commit()
    return changed


async def refresh_coverage(session: AsyncSession) -> None:
    rows = (await session.execute(select(VenueSymbol).where(VenueSymbol.is_active.is_(True)))).scalars().all()
    coverage: dict[int, dict[str, set[str]]] = {}
    for row in rows:
        item = coverage.setdefault(row.asset_id, {"spot": set(), "perp": set(), "orderbook": set()})
        if row.market_type == "spot":
            item["spot"].add(row.venue)
        if row.market_type == "perp":
            item["perp"].add(row.venue)
        item["orderbook"].add(row.venue)

    for asset_id, item in coverage.items():
        stmt = (
            insert(AssetDataCoverage)
            .values(
                asset_id=asset_id,
                has_spot=bool(item["spot"]),
                has_perp=bool(item["perp"]),
                has_orderbook=bool(item["orderbook"]),
                spot_venues=sorted(item["spot"]),
                perp_venues=sorted(item["perp"]),
            )
            .on_conflict_do_update(
                index_elements=[AssetDataCoverage.asset_id],
                set_={
                    "has_spot": bool(item["spot"]),
                    "has_perp": bool(item["perp"]),
                    "has_orderbook": bool(item["orderbook"]),
                    "spot_venues": sorted(item["spot"]),
                    "perp_venues": sorted(item["perp"]),
                },
            )
        )
        await session.execute(stmt)


async def update_universe(session: AsyncSession) -> int:
    candidates = await discover_all_venues()
    return await upsert_universe(session, candidates)
