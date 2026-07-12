"""
Unit tests for backend config — defaults and environment overrides.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSettingsDefaults:
    """Test that Settings picks up sensible defaults when env vars are absent."""

    def test_default_database_url(self):
        from app.config import Settings
        s = Settings()
        assert "trading_desk" in s.DATABASE_URL
        assert "postgresql://" in s.DATABASE_URL

    def test_default_celery_broker(self):
        from app.config import Settings
        s = Settings()
        assert "redis://" in s.CELERY_BROKER_URL

    def test_default_redis_event_channel(self):
        from app.config import Settings
        s = Settings()
        assert s.REDIS_EVENT_CHANNEL == "trading_events"

    def test_default_host_port(self):
        from app.config import Settings
        s = Settings()
        assert s.HOST == "0.0.0.0"
        assert s.PORT == 8000

    def test_settings_singleton(self):
        from app.config import get_settings
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_module_level_settings(self):
        from app.config import settings
        assert settings.APP_NAME == "AI Trading Desk"
        assert isinstance(settings.DEBUG, bool)

    def test_cors_defaults(self):
        from app.config import Settings
        s = Settings()
        assert s.CORS_ALLOW_ORIGINS == ["*"]
        assert s.CORS_ALLOW_CREDENTIALS is True


class TestSettingsEnvOverride:
    """Test that environment variables override defaults.

    Each test reloads the config module to defeat lru_cache caching.
    """

    def _reload_config(self):
        import importlib
        import app.config
        import app.database
        importlib.reload(app.config)
        # Re-import settings after reload
        from app.config import get_settings
        get_settings.cache_clear()

    def test_database_url_override(self):
        os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/testdb"
        try:
            import importlib
            import app.config
            importlib.reload(app.config)
            from app.config import get_settings
            get_settings.cache_clear()
            s = get_settings()
            assert "testdb" in s.DATABASE_URL
        finally:
            del os.environ["DATABASE_URL"]

    def test_debug_flag_true(self):
        os.environ["DEBUG"] = "true"
        try:
            import importlib
            import app.config
            importlib.reload(app.config)
            from app.config import get_settings
            get_settings.cache_clear()
            s = get_settings()
            assert s.DEBUG is True
        finally:
            del os.environ["DEBUG"]

    def test_debug_flag_false(self):
        os.environ["DEBUG"] = "false"
        try:
            import importlib
            import app.config
            importlib.reload(app.config)
            from app.config import get_settings
            get_settings.cache_clear()
            s = get_settings()
            assert s.DEBUG is False
        finally:
            del os.environ["DEBUG"]

    def test_event_channel_override(self):
        os.environ["REDIS_EVENT_CHANNEL"] = "custom_channel"
        try:
            import importlib
            import app.config
            importlib.reload(app.config)
            from app.config import get_settings
            get_settings.cache_clear()
            s = get_settings()
            assert s.REDIS_EVENT_CHANNEL == "custom_channel"
        finally:
            del os.environ["REDIS_EVENT_CHANNEL"]
