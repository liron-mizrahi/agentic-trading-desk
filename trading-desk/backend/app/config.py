"""Application configuration from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://admin:tradingdesk@db:5432/trading_desk",
    )
    DATABASE_URL_ASYNC: str = os.getenv(
        "DATABASE_URL_ASYNC",
        "postgresql+asyncpg://admin:tradingdesk@db:5432/trading_desk",
    )

    # Celery
    CELERY_BROKER_URL: str = os.getenv(
        "CELERY_BROKER_URL", "redis://redis:6379/0"
    )
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND", "redis://redis:6379/0"
    )

    # Redis (Pub/Sub)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    REDIS_EVENT_CHANNEL: str = os.getenv(
        "REDIS_EVENT_CHANNEL", "trading_events"
    )

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # CORS
    CORS_ALLOW_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # App
    APP_NAME: str = "AI Trading Desk"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Module-level singleton for direct import
settings = get_settings()
