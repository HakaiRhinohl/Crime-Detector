from __future__ import annotations

import logging

import httpx

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


async def send_telegram_message(message: str) -> bool:
    settings = get_settings()
    if settings.telegram_dry_run:
        logger.info("Telegram dry run", extra={"message": message[:500]})
        return False
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram is enabled but token/chat id are missing")
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            url,
            json={
                "chat_id": settings.telegram_chat_id,
                "text": message,
                "disable_web_page_preview": False,
            },
        )
        response.raise_for_status()
    return True

