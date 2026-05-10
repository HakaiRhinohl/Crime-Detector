from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def floor_time(ts: datetime | None = None, seconds: int = 60) -> datetime:
    ts = ts or utc_now()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=UTC)


def ago(minutes: int) -> datetime:
    return utc_now() - timedelta(minutes=minutes)

