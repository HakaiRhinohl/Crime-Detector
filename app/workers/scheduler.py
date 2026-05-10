from __future__ import annotations

import asyncio
import logging

from app.db.session import AsyncSessionLocal
from app.universe.update_universe import update_universe
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)


async def main_async() -> None:
    configure_logging()
    async with AsyncSessionLocal() as session:
        try:
            changed = await update_universe(session)
            logger.info("Initial universe update complete", extra={"changed": changed})
        except Exception:
            logger.exception("Initial universe update failed")
            await session.rollback()
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main_async())

