from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://scanner:scanner@localhost:5432/scanner"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    api_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_dry_run: bool = True
    telegram_daily_cap: Annotated[int, Field(ge=0)] = 3

    hydromancer_api_key: str | None = None
    hydromancer_base_url: str = "https://api.hydromancer.xyz"
    upbit_base_url: str = "https://api.upbit.com"

    universe_update_seconds: Annotated[int, Field(ge=60)] = 21600
    market_data_seconds: Annotated[int, Field(ge=10)] = 60
    orderbook_seconds: Annotated[int, Field(ge=30)] = 300
    dex_seconds: Annotated[int, Field(ge=60)] = 900
    features_seconds: Annotated[int, Field(ge=30)] = 300
    alerts_seconds: Annotated[int, Field(ge=30)] = 300

    http_timeout_seconds: Annotated[float, Field(gt=0)] = 20.0
    http_retries: Annotated[int, Field(ge=0)] = 2

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def alembic_database_url(self) -> str:
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
