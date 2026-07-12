"""
Unit tests for agent config module.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAgentConfigDefaults:
    """Agent config module defaults (now DeepSeek-native)."""

    def test_database_url_default(self):
        from agent import config
        assert "trading_desk" in config.DATABASE_URL
        assert "postgresql://" in config.DATABASE_URL

    def test_celery_broker_url(self):
        from agent import config
        assert "redis://" in config.CELERY_BROKER_URL

    def test_llm_deepseek_defaults(self):
        from agent import config
        assert config.OPENAI_BASE_URL == "https://api.deepseek.com/v1"
        assert config.OPENAI_MODEL == "deepseek-chat"
        assert config.LLM_MAX_RETRIES == 3
        assert config.LLM_TIMEOUT_SECONDS == 60

    def test_strategy_params(self):
        from agent import config
        assert config.CHOP_THRESHOLD == 38.2
        assert config.SMA200_CHECK is True
        assert config.DEFAULT_SECTOR == "Technology"

    def test_beat_schedule(self):
        from agent import config
        assert config.BEAT_SCREENER_HOUR == 23
        assert config.BEAT_SCREENER_MINUTE == 0

    def test_redis_pubsub_channel(self):
        from agent import config
        assert config.REDIS_PUBSUB_CHANNEL == "trading_events"

    def test_environment(self):
        from agent import config
        assert config.ENVIRONMENT in ("development", "production", "staging")

    def test_api_key_reads_from_deepseek_env(self):
        os.environ["DEEPSEEK_API_KEY"] = "sk-test-12345"
        try:
            import importlib
            import agent.config
            importlib.reload(agent.config)
            assert agent.config.OPENAI_API_KEY == "sk-test-12345"
        finally:
            del os.environ["DEEPSEEK_API_KEY"]
            importlib.reload(agent.config)


class TestAgentConfigEnvOverride:
    """Environment variable overrides for agent config."""

    def test_deepseek_model_override(self):
        os.environ["DEEPSEEK_MODEL"] = "deepseek-chat"
        try:
            import importlib
            import agent.config
            importlib.reload(agent.config)
            assert agent.config.OPENAI_MODEL == "deepseek-chat"
        finally:
            del os.environ["DEEPSEEK_MODEL"]
            importlib.reload(agent.config)

    def test_beat_schedule_override(self):
        os.environ["BEAT_SCREENER_HOUR"] = "22"
        try:
            import importlib
            import agent.config
            importlib.reload(agent.config)
            assert agent.config.BEAT_SCREENER_HOUR == 22
        finally:
            del os.environ["BEAT_SCREENER_HOUR"]
            importlib.reload(agent.config)

    def test_sector_override(self):
        os.environ["DEFAULT_SECTOR"] = "Healthcare"
        try:
            import importlib
            import agent.config
            importlib.reload(agent.config)
            assert agent.config.DEFAULT_SECTOR == "Healthcare"
        finally:
            del os.environ["DEFAULT_SECTOR"]
            importlib.reload(agent.config)
