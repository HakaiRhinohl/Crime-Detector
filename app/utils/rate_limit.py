from __future__ import annotations

import asyncio
import time


class AsyncTokenBucket:
    def __init__(self, rate_per_second: float, capacity: int | None = None) -> None:
        self.rate_per_second = rate_per_second
        self.capacity = float(capacity or max(1, int(rate_per_second)))
        self.tokens = self.capacity
        self.updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, cost: float = 1.0) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.updated_at
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_second)
                self.updated_at = now
                if self.tokens >= cost:
                    self.tokens -= cost
                    return
                missing = cost - self.tokens
                await asyncio.sleep(missing / self.rate_per_second)

