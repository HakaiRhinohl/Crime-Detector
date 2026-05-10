from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.backtest.evaluate_alerts import evaluate_alert
from app.db.models import Alert
from app.db.session import AsyncSessionLocal
from app.utils.logging import configure_logging


async def main_async() -> None:
    configure_logging()
    async with AsyncSessionLocal() as session:
        alerts = (await session.execute(select(Alert).order_by(Alert.ts.desc()).limit(500))).scalars().all()
        outcomes = [await evaluate_alert(session, alert) for alert in alerts]
        print(json.dumps([outcome.__dict__ for outcome in outcomes], default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main_async())

