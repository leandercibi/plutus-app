"""Tests for Plutus configuration module."""

import os
import pytest
from pydantic import ValidationError

from plutus.config import Settings, get_settings


class TestConfigLoading:
    """Test configuration loading from environment variables."""
    
    def test_load_with_required_fields(self, mock_env_vars):
        """Test config loads successfully with required fields."""
        settings = Settings()
        
        assert settings.OPENROUTER_API_KEY == "test-api-key-12345"
        assert settings.TELEGRAM_BOT_TOKEN == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        assert settings.TELEGRAM_CHAT_ID == "-1001234567890"
    
    def test_missing_required_field_raises_error(self, monkeypatch, tmp_path):
        """Test that missing required fields raise ValidationError."""
        from plutus.config import get_settings
        get_settings.cache_clear()
        
        # Change to temp directory without .env file
        monkeypatch.chdir(tmp_path)
        
        # Remove all required fields
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        error_dict = exc_info.value.errors()
        missing_fields = {err["loc"][0] for err in error_dict}
        
        assert "OPENROUTER_API_KEY" in missing_fields
        assert "TELEGRAM_BOT_TOKEN" in missing_fields
        assert "TELEGRAM_CHAT_ID" in missing_fields


class TestConfigDefaults:
    """Test default values for optional configuration fields."""
    
    def test_openrouter_defaults(self, mock_env_vars):
        """Test OpenRouter default values."""
        settings = Settings()
        
        assert settings.OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
        assert settings.DEEPSEEK_FAST_MODEL == "deepseek/deepseek-v4-flash"
        assert settings.DEEPSEEK_REASON_MODEL == "deepseek/deepseek-v4-flash"
    
    def test_database_defaults(self, mock_env_vars, monkeypatch, tmp_path):
        """Test database default values."""
        # Change to temp directory without .env file
        monkeypatch.chdir(tmp_path)
        # Remove DATABASE_URL override to test default
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from plutus.config import get_settings
        get_settings.cache_clear()
        
        settings = Settings()
        
        assert settings.DATABASE_URL == "postgresql://plutus:plutus@localhost:5432/plutus_db"
    
    def test_whatsapp_defaults(self, mock_env_vars):
        """Test WhatsApp default values."""
        settings = Settings()
        
        assert settings.WHATSAPP_PHONE == ""
        assert settings.WHATSAPP_API_KEY == ""
        assert settings.WHATSAPP_ENABLED is False
    
    def test_reddit_defaults(self, mock_env_vars):
        """Test Reddit default values."""
        settings = Settings()
        
        assert settings.REDDIT_CLIENT_ID == ""
        assert settings.REDDIT_CLIENT_SECRET == ""
        assert settings.REDDIT_USER_AGENT == "plutus-trading-bot/1.0"
        assert settings.REDDIT_ENABLED is False
    
    def test_api_defaults(self, mock_env_vars):
        """Test API default values."""
        settings = Settings()
        
        assert settings.API_SECRET_KEY == "change_this_in_production"
        assert settings.API_HOST == "0.0.0.0"
        assert settings.API_PORT == 8009
        assert settings.API_RATE_LIMIT_PER_HOUR == 30
        assert settings.ANALYZE_CACHE_TTL_SECONDS == 300
    
    def test_bot_internal_defaults(self, mock_env_vars):
        """Test bot internal defaults."""
        settings = Settings()
        
        assert settings.BOT_INTERNAL_HOST == "127.0.0.1"
        assert settings.BOT_INTERNAL_PORT == 8001
    
    def test_trading_parameter_defaults(self, mock_env_vars):
        """Test trading parameter defaults."""
        settings = Settings()
        
        assert settings.INITIAL_CAPITAL == 100_000.0
        assert settings.MAX_RISK_PCT == 5.0
        assert settings.MIN_RR_RATIO == 1.5
        assert settings.HOLD_DAYS_MIN == 3
        assert settings.HOLD_DAYS_MAX == 10
        assert settings.MAX_OPEN_POSITIONS_ADVISORY == 4
        assert settings.MAX_OPEN_POSITIONS_HARD == 10
        assert settings.RISK_PCT_PER_TRADE == 5.0
    
    def test_universe_filter_defaults(self, mock_env_vars):
        """Test universe filter defaults."""
        settings = Settings()
        
        assert settings.UNIVERSE_SEED_CSV == "plutus/data/seed_universe.csv"
        assert settings.UNIVERSE_PRICE_MIN == 50.0
        assert settings.UNIVERSE_PRICE_MAX == 5_000.0
        assert settings.UNIVERSE_MIN_AVG_VOLUME == 500_000
        assert settings.UNIVERSE_MIN_AVG_VALUE_CR == 10.0
    
    def test_news_defaults(self, mock_env_vars):
        """Test news configuration defaults."""
        settings = Settings()
        
        assert settings.NEWS_API_KEY == ""
        assert settings.NEWS_LOOKBACK_HOURS == 48
        assert settings.MATERIAL_KEYWORDS_YAML == "plutus/data/material_keywords.yaml"
        assert settings.MATERIAL_KEYWORD_TIERS == "A,B"
    
    def test_scheduler_defaults(self, mock_env_vars):
        """Test scheduler defaults."""
        settings = Settings()
        
        assert settings.WEEKLY_RUN_DAY == "sun"
        assert settings.WEEKLY_RUN_HOUR == 18
        assert settings.WEEKLY_RUN_MINUTE == 0
        assert settings.WEEKLY_REVALIDATE_DAY == "mon"
        assert settings.WEEKLY_REVALIDATE_HOUR == 9
        assert settings.WEEKLY_REVALIDATE_MINUTE == 10
        assert settings.NEWS_CHECK_INTERVAL_MINUTES == 30
        assert settings.MARKET_OPEN_HOUR == 9
        assert settings.MARKET_CLOSE_HOUR == 16
        assert settings.REJECTED_HEADLINES_RETENTION_DAYS == 30
    
    def test_backtest_defaults(self, mock_env_vars):
        """Test backtest defaults."""
        settings = Settings()
        
        assert settings.BACKTEST_LOOKBACK_DAYS == 90
        assert settings.BACKTEST_TOP_CANDIDATES == 20
    
    def test_reports_defaults(self, mock_env_vars):
        """Test reports defaults."""
        settings = Settings()
        
        assert settings.REPORTS_DIR == "src/reports/weekly"
        assert settings.NSE_HOLIDAYS_FILE == "plutus/data/nse_holidays.txt"


class TestConfigOverrides:
    """Test configuration overrides via environment variables."""
    
    def test_override_numeric_values(self, mock_env_vars, monkeypatch):
        """Test overriding numeric configuration values."""
        monkeypatch.setenv("INITIAL_CAPITAL", "200000.0")
        monkeypatch.setenv("MAX_RISK_PCT", "3.0")
        monkeypatch.setenv("API_PORT", "9000")
        
        settings = Settings()
        
        assert settings.INITIAL_CAPITAL == 200_000.0
        assert settings.MAX_RISK_PCT == 3.0
        assert settings.API_PORT == 9000
    
    def test_override_string_values(self, mock_env_vars, monkeypatch):
        """Test overriding string configuration values."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/testdb")
        monkeypatch.setenv("WEEKLY_RUN_DAY", "sat")
        
        settings = Settings()
        
        assert settings.DATABASE_URL == "postgresql://user:pass@host:5432/testdb"
        assert settings.WEEKLY_RUN_DAY == "sat"
    
    def test_override_boolean_values(self, mock_env_vars, monkeypatch):
        """Test overriding boolean configuration values."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("REDDIT_ENABLED", "1")
        
        settings = Settings()
        
        assert settings.WHATSAPP_ENABLED is True
        assert settings.REDDIT_ENABLED is True


class TestConfigCaching:
    """Test configuration caching behavior."""
    
    def test_get_settings_returns_cached_instance(self, mock_env_vars):
        """Test that get_settings() returns the same cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        
        assert settings1 is settings2
    
    def test_settings_singleton_behavior(self, mock_env_vars):
        """Test that settings behaves as a singleton."""
        from plutus.config import settings as imported_settings
        
        cached_settings = get_settings()
        
        # Both should have the same values
        assert imported_settings.OPENROUTER_API_KEY == cached_settings.OPENROUTER_API_KEY
        assert imported_settings.TELEGRAM_BOT_TOKEN == cached_settings.TELEGRAM_BOT_TOKEN


class TestConfigValidation:
    """Test configuration validation logic."""
    
    def test_case_insensitive_env_vars(self, monkeypatch):
        """Test that environment variables are case-insensitive."""
        monkeypatch.setenv("openrouter_api_key", "test-key-lowercase")
        monkeypatch.setenv("telegram_bot_token", "test-token")
        monkeypatch.setenv("telegram_chat_id", "test-chat-id")
        
        settings = Settings()
        
        assert settings.OPENROUTER_API_KEY == "test-key-lowercase"
    
    def test_invalid_numeric_type_raises_error(self, mock_env_vars, monkeypatch):
        """Test that invalid numeric types raise ValidationError."""
        monkeypatch.setenv("API_PORT", "not_a_number")
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        errors = exc_info.value.errors()
        assert any("API_PORT" in str(err["loc"]) for err in errors)
    
    def test_invalid_float_type_raises_error(self, mock_env_vars, monkeypatch):
        """Test that invalid float types raise ValidationError."""
        monkeypatch.setenv("INITIAL_CAPITAL", "invalid_float")
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        errors = exc_info.value.errors()
        assert any("INITIAL_CAPITAL" in str(err["loc"]) for err in errors)
