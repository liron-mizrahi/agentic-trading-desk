"""
Agent Layer configuration — sourced from environment variables with sensible defaults.
"""

import os


def _str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, str(default)).strip().lower()
    return val in ("1", "true", "yes", "y", "on")


# ── Database ──────────────────────────────────────────────────────────
DATABASE_URL: str = _str(
    "DATABASE_URL",
    "postgresql://admin:***@localhost:5432/trading_desk",
)

# ── Celery / Redis ────────────────────────────────────────────────────
CELERY_BROKER_URL: str = _str("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND: str = _str("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# ── LLM — DeepSeek (OpenAI-compatible) ───────────────────────────────
OPENAI_API_KEY: str = _str("DEEPSEEK_API_KEY", "")
OPENAI_BASE_URL: str = _str("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
OPENAI_MODEL: str = _str("DEEPSEEK_MODEL", "deepseek-chat")
LLM_MAX_RETRIES: int = int(_str("LLM_MAX_RETRIES", "3"))
LLM_TIMEOUT_SECONDS: int = int(_str("LLM_TIMEOUT_SECONDS", "60"))

# ── Redis Pub/Sub ─────────────────────────────────────────────────────
REDIS_PUBSUB_CHANNEL: str = _str("REDIS_PUBSUB_CHANNEL", "trading_events")
REDIS_HOST: str = _str("REDIS_HOST", "localhost")
REDIS_PORT: int = int(_str("REDIS_PORT", "6379"))
REDIS_DB: int = int(_str("REDIS_DB", "0"))

# ── Strategy parameters ──────────────────────────────────────────────
DEFAULT_SECTOR: str = _str("DEFAULT_SECTOR", "Technology")
CHOP_THRESHOLD: float = 38.2
SMA200_CHECK: bool = _bool("SMA200_CHECK", True)

# ── Celery Beat schedule ─────────────────────────────────────────────
BEAT_SCREENER_HOUR: int = int(_str("BEAT_SCREENER_HOUR", "23"))
BEAT_SCREENER_MINUTE: int = int(_str("BEAT_SCREENER_MINUTE", "0"))
BEAT_SCREENER_DAYS: str = _str("BEAT_SCREENER_DAYS", "mon-fri")

# ── Environment ──────────────────────────────────────────────────────
ENVIRONMENT: str = _str("ENVIRONMENT", "development")
LOG_LEVEL: str = _str("LOG_LEVEL", "INFO")
