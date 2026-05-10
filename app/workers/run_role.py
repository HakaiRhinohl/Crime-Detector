from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable

from app.alerts.engine import process_alerts
from app.collectors.dex_context import collect_dex_snapshots
from app.collectors.hydromancer_store import collect_hl_liquidation_clusters
from app.collectors.market_data import collect_market_snapshots
from app.config.settings import get_settings
from app.db.session import AsyncSessionLocal
from app.features.build_features import build_latest_features
from app.orderbooks.snapshots import collect_orderbook_snapshots
from app.universe.update_universe import update_universe
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)


async def run_forever(role: str) -> None:
    settings = get_settings()
    handlers: dict[str, tuple[int, Callable]] = {
        "universe": (settings.universe_update_seconds, update_universe),
        "market_data": (settings.market_data_seconds, collect_market_snapshots),
        "orderbooks": (settings.orderbook_seconds, collect_orderbook_snapshots),
        "dex": (settings.dex_seconds, collect_dex_snapshots),
        "hydromancer": (settings.alerts_seconds, collect_hl_liquidation_clusters),
        "hyperliquid": (settings.market_data_seconds, collect_market_snapshots),
        "features": (settings.features_seconds, build_latest_features),
        "alerts": (settings.alerts_seconds, process_alerts),
    }
    if role not in handlers:
        raise SystemExit(f"Unknown worker role: {role}")
    cadence, handler = handlers[role]
    while True:
        async with AsyncSessionLocal() as session:
            try:
                count = await handler(session)
                logger.info("Worker run complete", extra={"role": role, "count": count})
            except Exception:
                logger.exception("Worker run failed", extra={"role": role})
                await session.rollback()
        await asyncio.sleep(cadence)


def main() -> None:
    configure_logging()
    role = sys.argv[1] if len(sys.argv) > 1 else "market_data"
    asyncio.run(run_forever(role))


if __name__ == "__main__":
    main()

