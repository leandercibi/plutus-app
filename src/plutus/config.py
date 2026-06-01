"""Plutus configuration — single source of truth for all settings.

All values are loaded from .env (or environment variables). See
specs/03_config_env.md for the canonical contract.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- OpenRouter / LLM ---
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    DEEPSEEK_FAST_MODEL: str = "deepseek/deepseek-v4-flash"
    DEEPSEEK_REASON_MODEL: str = "deepseek/deepseek-v4-flash"

    # --- Database ---
    DATABASE_URL: str = "postgresql://plutus:plutus@localhost:5432/plutus_db"

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str

    # --- WhatsApp (CallMeBot) ---
    WHATSAPP_PHONE: str = ""
    WHATSAPP_API_KEY: str = ""
    WHATSAPP_ENABLED: bool = False

    # --- News ---
    NEWS_API_KEY: str = ""
    NEWS_LOOKBACK_HOURS: int = 48

    # --- Reddit ---
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "plutus-trading-bot/1.0"
    REDDIT_ENABLED: bool = False

    # --- Internal API (plutus-main; FastAPI on 8000) ---
    API_SECRET_KEY: str = "change_this_in_production"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # --- API rate limit + symbol cache ---
    API_RATE_LIMIT_PER_HOUR: int = 30
    ANALYZE_CACHE_TTL_SECONDS: int = 300

    # --- Bot internal IPC (plutus-bot; FastAPI on 127.0.0.1:8001) ---
    BOT_INTERNAL_HOST: str = "127.0.0.1"
    BOT_INTERNAL_PORT: int = 8001

    # --- Trading Parameters ---
    INITIAL_CAPITAL: float = 100_000.0
    MAX_RISK_PCT: float = 5.0
    MIN_RR_RATIO: float = 1.5
    HOLD_DAYS_MIN: int = 3
    HOLD_DAYS_MAX: int = 10

    # --- Position sizing (advisory + hard caps; see _CHANGE_SPEC.md §3) ---
    MAX_OPEN_POSITIONS_ADVISORY: int = 4
    MAX_OPEN_POSITIONS_HARD: int = 10
    RISK_PCT_PER_TRADE: float = 5.0

    # --- Universe Filters (see _CHANGE_SPEC.md §2) ---
    UNIVERSE_SEED_CSV: str = "plutus/data/seed_universe.csv"
    UNIVERSE_PRICE_MIN: float = 50.0
    UNIVERSE_PRICE_MAX: float = 5_000.0
    UNIVERSE_MIN_AVG_VOLUME: int = 500_000
    UNIVERSE_MIN_AVG_VALUE_CR: float = 10.0

    # --- News prefilter (see _CHANGE_SPEC.md §5) ---
    MATERIAL_KEYWORDS_YAML: str = "plutus/data/material_keywords.yaml"
    MATERIAL_KEYWORD_TIERS: str = "A,B"

    # --- Scheduler (see _CHANGE_SPEC.md §10) ---
    WEEKLY_RUN_DAY: str = "sun"
    WEEKLY_RUN_HOUR: int = 18
    WEEKLY_RUN_MINUTE: int = 0
    WEEKLY_REVALIDATE_DAY: str = "mon"
    WEEKLY_REVALIDATE_HOUR: int = 9
    WEEKLY_REVALIDATE_MINUTE: int = 10
    NEWS_CHECK_INTERVAL_MINUTES: int = 30
    MARKET_OPEN_HOUR: int = 9
    MARKET_CLOSE_HOUR: int = 16
    REJECTED_HEADLINES_RETENTION_DAYS: int = 30

    # --- Backtest ---
    BACKTEST_LOOKBACK_DAYS: int = 90
    BACKTEST_TOP_CANDIDATES: int = 20

    # --- Reports ---
    REPORTS_DIR: str = "src/reports/weekly"
    NSE_HOLIDAYS_FILE: str = "plutus/data/nse_holidays.txt"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
