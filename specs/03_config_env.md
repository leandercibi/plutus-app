# 03 — Configuration & Environment Variables

---

## `requirements.txt`

```txt
# Core
fastapi==0.111.0
uvicorn[standard]==0.30.1
apscheduler==3.10.4
python-dotenv==1.0.1
pydantic-settings==2.3.4
slowapi==0.1.9
pyyaml==6.0.1

# Database
sqlalchemy==2.0.31
psycopg2-binary==2.9.9
alembic==1.13.2

# Data
yfinance==0.2.43
pandas==2.2.2
numpy==1.26.4
pandas-ta==0.3.14b0
requests==2.32.3
feedparser==6.0.11
beautifulsoup4==4.12.3
lxml==5.2.2

# Reddit
praw==7.7.1

# Mutual Funds
mftool==0.2.9

# LLM / Agents
openai==1.40.0
langgraph==0.2.28
langchain-core==0.2.38

# Backtrader
backtrader==1.9.78.123

# Telegram
python-telegram-bot==21.4

# Streamlit / Dashboard
streamlit==1.37.1
plotly==5.22.0
altair==5.3.0

# Utilities
httpx==0.27.0
tenacity==8.4.2
structlog==24.2.0
```

New additions:
- `slowapi==0.1.9` — sliding-window rate limiter for `/analyze` (see §6 of `_CHANGE_SPEC.md`).
- `pyyaml==6.0.1` — loads `material_keywords.yaml` for the news prefilter (see §5).
- `httpx==0.27.0` — already present; used by `plutus-main` for async `POST` to `plutus-bot`'s internal IPC endpoints (see §9).

---

## `config.py` — Full Implementation

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
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
    DEEPSEEK_FAST_MODEL: str = "deepseek/deepseek-v4-flash"        # all agents (V4 Flash)
    DEEPSEEK_REASON_MODEL: str = "deepseek/deepseek-v4-flash"      # synthesizer (V4 Flash; swap to a heavier reasoner later if needed)

    # --- Database ---
    DATABASE_URL: str = "postgresql://plutus:plutus@localhost:5432/plutus_db"

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str                                          # your personal chat ID

    # --- WhatsApp (CallMeBot) ---
    WHATSAPP_PHONE: str = ""                                       # +91XXXXXXXXXX format
    WHATSAPP_API_KEY: str = ""
    WHATSAPP_ENABLED: bool = False

    # --- News ---
    NEWS_API_KEY: str = ""                                         # newsapi.org free tier
    NEWS_LOOKBACK_HOURS: int = 48

    # --- Reddit ---
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "plutus-trading-bot/1.0"
    REDDIT_ENABLED: bool = False                                   # set True when keys available

    # --- Internal API (plutus-main; FastAPI on 8000) ---
    API_SECRET_KEY: str = "change_this_in_production"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # --- API rate limit + symbol cache ---
    API_RATE_LIMIT_PER_HOUR: int = 30                              # per-API-key sliding window (slowapi)
    ANALYZE_CACHE_TTL_SECONDS: int = 300                           # 5-minute symbol-level cache

    # --- Bot internal IPC (plutus-bot; FastAPI on 127.0.0.1:8001) ---
    BOT_INTERNAL_HOST: str = "127.0.0.1"
    BOT_INTERNAL_PORT: int = 8001

    # --- Trading Parameters ---
    INITIAL_CAPITAL: float = 100_000.0                             # ₹1,00,000
    MAX_RISK_PCT: float = 5.0                                      # 5% per trade
    MIN_RR_RATIO: float = 1.5                                      # minimum reward:risk
    HOLD_DAYS_MIN: int = 3
    HOLD_DAYS_MAX: int = 10

    # --- Position sizing (advisory + hard caps; see _CHANGE_SPEC.md §3) ---
    MAX_OPEN_POSITIONS_ADVISORY: int = 4                           # soft warning above this
    MAX_OPEN_POSITIONS_HARD: int = 10                              # hard cap; cannot exceed
    RISK_PCT_PER_TRADE: float = 5.0                                # warn if (entry-stop)*shares > 5% of initial_capital

    # --- Universe Filters (see _CHANGE_SPEC.md §2) ---
    UNIVERSE_SEED_CSV: str = "src/plutus/data/seed_universe.csv"   # Nifty 500 + MidCap 150 seed
    UNIVERSE_PRICE_MIN: float = 50.0
    UNIVERSE_PRICE_MAX: float = 5_000.0
    UNIVERSE_MIN_AVG_VOLUME: int = 500_000                         # 5,00,000 shares avg over 30d
    UNIVERSE_MIN_AVG_VALUE_CR: float = 10.0                        # ₹10 Cr daily traded value (replaces market cap)
    # DROPPED: UNIVERSE_MIN_MCAP_CR (no longer used; replaced by UNIVERSE_MIN_AVG_VALUE_CR)

    # --- News prefilter (see _CHANGE_SPEC.md §5) ---
    MATERIAL_KEYWORDS_YAML: str = "src/plutus/data/material_keywords.yaml"
    MATERIAL_KEYWORD_TIERS: str = "A,B"                            # comma-separated; tier C is in YAML but disabled by default

    # --- Scheduler (see _CHANGE_SPEC.md §10) ---
    WEEKLY_RUN_DAY: str = "sun"                                    # Sunday research run
    WEEKLY_RUN_HOUR: int = 18                                      # 18:00 IST
    WEEKLY_RUN_MINUTE: int = 0
    WEEKLY_REVALIDATE_DAY: str = "mon"                             # NEW — Monday gap re-validation
    WEEKLY_REVALIDATE_HOUR: int = 9                                # NEW — 09:10 IST (10 min after open)
    WEEKLY_REVALIDATE_MINUTE: int = 10                             # NEW
    NEWS_CHECK_INTERVAL_MINUTES: int = 60                          # hourly news scan during market hours
    MARKET_OPEN_HOUR: int = 9
    MARKET_CLOSE_HOUR: int = 16
    REJECTED_HEADLINES_RETENTION_DAYS: int = 30                    # NEW — daily 03:00 IST cleanup

    # --- Backtest ---
    BACKTEST_LOOKBACK_DAYS: int = 90
    BACKTEST_TOP_CANDIDATES: int = 20                              # top N from universe to run agents on

    # --- Reports ---
    REPORTS_DIR: str = "src/reports/weekly"
    NSE_HOLIDAYS_FILE: str = "src/plutus/data/nse_holidays.txt"    # NEW — used by trading-day math in outcome tracker


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

---

## `.env` Template

```env
# Copy this to .env and fill in real values
# NEVER commit .env to git
#
# Notes on the new vars introduced in _CHANGE_SPEC.md:
#   MATERIAL_KEYWORD_TIERS   Which keyword tiers in material_keywords.yaml are
#                            enabled for the news prefilter. Default "A,B".
#                            Set to "A,B,C" to also enable Tier C corporate-actions
#                            keywords (buyback/split/bonus/etc).
#   BOT_INTERNAL_PORT        Port that plutus-bot binds (loopback only) to receive
#                            push commands from plutus-main. Default 8001.
#   API_RATE_LIMIT_PER_HOUR  Sliding-window cap on /analyze per API key. Default 30.
#   ANALYZE_CACHE_TTL_SECONDS  Symbol-level cache TTL shared by /analyze, /stock,
#                              and the dashboard "Run on-demand" button. Default 300.
#
# DEEPSEEK_FAST_MODEL and DEEPSEEK_REASON_MODEL default to "deepseek/deepseek-v4-flash"
# in config.py — do not override unless you intentionally want a different model.

# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-...

# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=987654321

# News
NEWS_API_KEY=your_newsapi_key

# Reddit (optional)
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_ENABLED=false

# WhatsApp (optional)
WHATSAPP_PHONE=+91XXXXXXXXXX
WHATSAPP_API_KEY=your_callmebot_key
WHATSAPP_ENABLED=false

# Internal API
API_SECRET_KEY=generate_with_python_secrets_token_hex_32
API_RATE_LIMIT_PER_HOUR=30

# Bot internal IPC (loopback only)
BOT_INTERNAL_PORT=8001

# News prefilter — set to A,B,C to enable Tier C corporate-actions keywords
MATERIAL_KEYWORD_TIERS=A,B

# Database (default works if you follow 15_deployment.md)
DATABASE_URL=postgresql://plutus:plutus@localhost:5432/plutus_db
```

---

## How Config Is Used Across Modules

```python
# Every module that needs config does this:
from plutus.config import settings

# Example usage:
openai_client = OpenAI(
    api_key=settings.OPENROUTER_API_KEY,
    base_url=settings.OPENROUTER_BASE_URL,
)

# Database URL:
engine = create_engine(settings.DATABASE_URL)

# Risk calculation:
max_loss = settings.INITIAL_CAPITAL * (settings.MAX_RISK_PCT / 100)  # = 5000

# plutus-main → plutus-bot push (see _CHANGE_SPEC.md §9):
import httpx
async with httpx.AsyncClient() as cli:
    await cli.post(
        f"http://{settings.BOT_INTERNAL_HOST}:{settings.BOT_INTERNAL_PORT}/push/weekly-summary",
        json={"run_id": run_id},
        timeout=10,
    )
```

---

## IST Timezone Note

All scheduled times in config are in **IST (Indian Standard Time, UTC+5:30)**.
When running APScheduler, set timezone explicitly:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Kolkata"))
```

Add `pytz==2024.1` to requirements.txt.
