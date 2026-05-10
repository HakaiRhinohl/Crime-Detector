from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class HTTPClient:
    def __init__(
        self,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout or settings.http_timeout_seconds,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)),
        wait=wait_exponential_jitter(initial=0.25, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = await self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)),
        wait=wait_exponential_jitter(initial=0.25, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def post_json(self, path: str, json: dict[str, Any] | None = None) -> Any:
        response = await self.client.post(path, json=json)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.content


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.debug("Could not parse float", extra={"value": value})
        return None


def compact_raw(raw: dict[str, Any], max_items: int = 30) -> dict[str, Any]:
    if len(raw) <= max_items:
        return raw
    return {key: raw[key] for key in list(raw.keys())[:max_items]}

