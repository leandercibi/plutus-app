# 02 — Folder Structure

> Exact file tree for `plutus-app/`. Create every file listed here.
> Files marked **[AUTO]** are generated at runtime and must not be committed.
> Files marked **[CHECKED-IN]** are static project assets that ship with the repo.

Project root: `/Users/leander/personal-projects/plutus-app/` (OCI: `/home/ubuntu/plutus-app/`).
Code root: `src/`. Top-level Python package: `plutus` (imports look like `from plutus.data.ohlcv import fetch_ohlcv`).

---

## Complete File Tree

```
plutus-app/
├── specs/                          # the spec files (this folder)
├── src/
│   ├── main.py
│   ├── bot.py                      # NEW — separate telegram process
│   ├── dashboard.py
│   ├── requirements.txt
│   ├── .env                        # gitignored
│   ├── .gitignore                  # excludes .env, __pycache__, .venv, reports/, data/.cache/
│   ├── plutus/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── data/
│   │   │   ├── __init__.py
│   │   │   ├── universe.py
│   │   │   ├── seed_universe.csv          # Nifty 500 + MidCap 150
│   │   │   ├── ohlcv.py
│   │   │   ├── news.py
│   │   │   ├── material_keywords.yaml     # NEW — tiered prefilter
│   │   │   ├── reddit.py
│   │   │   ├── smart_money.py
│   │   │   ├── nse_holidays.txt           # NEW — for trading-day calc
│   │   │   ├── fno_ban_list.txt           # daily refreshed
│   │   │   └── .cache/                    # runtime; gitignored
│   │   ├── strategies/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── bundle_trend.py
│   │   │   ├── bundle_reversal.py
│   │   │   ├── bundle_breakout.py
│   │   │   ├── bundle_smc.py
│   │   │   └── bundle_composite.py        # peer bundle (5 of 5), 3-of-4 inner gate
│   │   ├── backtesting/
│   │   │   ├── __init__.py
│   │   │   ├── runner.py
│   │   │   └── paper_trader.py
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── openrouter_client.py
│   │   │   ├── prompts.py
│   │   │   ├── technical.py
│   │   │   ├── sentiment.py
│   │   │   ├── smart_money.py
│   │   │   ├── risk_manager.py
│   │   │   ├── synthesizer.py
│   │   │   └── graph.py
│   │   ├── alerts/
│   │   │   ├── __init__.py
│   │   │   ├── telegram_bot.py
│   │   │   └── whatsapp.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   │   └── cache.py                   # NEW — 5-min symbol cache + rate limit
│   │   └── db/
│   │       ├── __init__.py
│   │       ├── models.py
│   │       ├── session.py
│   │       ├── schema.sql
│   │       └── init_db.py
│   ├── scripts/
│   │   └── refresh_seed_universe.py       # NEW — manual run
│   └── reports/
│       └── weekly/                        # gitignored
└── README.md
```

---

## Entry Points (`src/*.py`)

Three independent processes, each its own systemd unit (`plutus-main`, `plutus-bot`, `plutus-dashboard`).

### `src/main.py` — `plutus-main.service` [CHECKED-IN]
- Boots **FastAPI on port 8000** (public API: `/analyze`, `/weekly`, `/health`).
- Boots **APScheduler** with five jobs: `weekly_pipeline`, `weekly_revalidate`, `news_monitor`, `outcome_tracker`, `rejected_headlines_cle` (see `12_scheduler.md`).
- Pushes to the bot via loopback HTTP: `httpx.post("http://127.0.0.1:8001/push/...")`. Bot-down failures are logged warnings, never fatal.
- Imports from `plutus.api.routes`, `plutus.db`, `plutus.agents.graph`, etc. Does NOT import `plutus.alerts.telegram_bot` directly.

### `src/bot.py` — `plutus-bot.service` [CHECKED-IN]
- Boots **python-telegram-bot Application** in polling mode.
- Boots a **second FastAPI app on `127.0.0.1:8001`** (loopback only, no auth) that exposes `POST /push/weekly-summary` and `POST /push/news-alert` for `plutus-main` to call.
- Reads PostgreSQL directly for `/portfolio`, `/stock`, `/buy`, `/sell`, `/watch`, `/history` handlers.
- Calls `plutus-main`'s `/analyze` (with API key) for `/stock SYMBOL` so it benefits from the shared 5-min cache.
- Imports `plutus.alerts.telegram_bot.{build_telegram_app, register_internal_routes}` and the command handlers.

### `src/dashboard.py` — `plutus-dashboard.service` [CHECKED-IN]
- `streamlit run src/dashboard.py --server.port 8501`.
- Reads PostgreSQL directly via `plutus.db.session.SessionLocal`. Renders all 8 tabs (Home, Signals, Portfolio, Strategy Lab, News Feed, Watchlist, History, Settings).

### `src/requirements.txt` [CHECKED-IN]
Pinned dependencies (see `15_deployment.md` for the exact list).

### `src/.env` [NOT COMMITTED]
Environment variables loaded by `plutus.config`. See `03_config_env.md`.

### `src/.gitignore` [CHECKED-IN]
Excludes `.env`, `__pycache__/`, `.venv/`, `reports/`, `plutus/data/.cache/`, `*.pyc`, `*.db`, `.DS_Store`.

---

## `plutus/` Package

### `plutus/__init__.py` [CHECKED-IN]
Empty (or `__version__ = "0.1.0"`).

### `plutus/config.py` [CHECKED-IN]
Pydantic `Settings` class. Loads from `.env`. Single source of truth for every tunable: API keys, DB URL, scheduler timezones, universe filters (`UNIVERSE_PRICE_MIN/MAX`, `UNIVERSE_MIN_AVG_VOLUME`, `UNIVERSE_MIN_AVG_VALUE_CR`), DeepSeek model IDs (`DEEPSEEK_FAST_MODEL`, `DEEPSEEK_REASON_MODEL` — both default to `deepseek/deepseek-v4-flash`), `MAX_OPEN_POSITIONS_ADVISORY=4`, `MAX_OPEN_POSITIONS_HARD=10`, `MATERIAL_KEYWORD_TIERS="A,B"`, `BOT_INTERNAL_PORT=8001`, `BOT_INTERNAL_BIND="127.0.0.1"`. See `03_config_env.md` for the full list.

---

### `plutus/data/`

#### `data/__init__.py` [CHECKED-IN]
Empty.

#### `data/universe.py` [CHECKED-IN]
NSE universe screener built on a static seed list — **no `yfinance.Ticker.info` calls.**
- `load_seed_universe() -> List[Tuple[symbol, exchange, segment]]` — reads `data/seed_universe.csv`.
- `get_universe() -> List[str]` — reads seed CSV → fetches 90-day OHLCV per symbol via `data.ohlcv.fetch_ohlcv` → applies price/volume/traded-value filters → drops F&O ban-listed symbols → caches result to `data/.cache/universe_<weekof>.json`.
- `_load_fno_ban_list() -> Set[str]` — reads `data/fno_ban_list.txt`; if older than 24h, best-effort refresh from NSE; on failure, use stale file with logged warning.

#### `data/seed_universe.csv` [CHECKED-IN]
Columns: `symbol,exchange,segment` (`segment ∈ {LARGE_CAP, MID_CAP}`). Initial content: Nifty 500 + Nifty MidCap 150 constituents (~650 unique rows). Refreshed manually monthly via `scripts/refresh_seed_universe.py`.

#### `data/ohlcv.py` [CHECKED-IN]
Historical + live price fetcher.
- `fetch_ohlcv(symbol, days=90, interval="1d") -> pd.DataFrame`
- `fetch_live_price(symbol) -> float`
- Uses yfinance (`SYMBOL.NS`), ~15-min delayed during market hours. Disk-cached under `data/.cache/`.

#### `data/news.py` [CHECKED-IN]
RSS-driven headline fetcher + tiered prefilter + batched DeepSeek classifier.
- `fetch_news(symbol, hours=48) -> List[Dict]` — pulls from configured RSS feeds and tags each headline with `symbol`, `source`, `published_at`.
- `prefilter_headlines(headlines: List[Dict]) -> List[Dict]` — keeps headlines that hit any enabled tier in `material_keywords.yaml` and don't hit the stoplist; tags each input with `filter_status ∈ {"kept", "stoplist", "no_keyword"}`.
- `classify_news(symbol: str, headlines: List[Dict]) -> Dict` — runs prefilter; if nothing survives, calls `save_rejected_headlines` and returns a neutral verdict (no LLM call); otherwise issues a single batched LLM call across all kept headlines for the symbol.
- `save_rejected_headlines(symbol: str, rejected: List[Dict]) -> None` — bulk inserts into `rejected_headlines` table with `filter_status` set.

#### `data/material_keywords.yaml` [CHECKED-IN] — NEW
Three-tier keyword list (`tier_A`, `tier_B`, `tier_C`) plus `stoplist`. Default enabled tiers via `MATERIAL_KEYWORD_TIERS=A,B`. Full content lives in `_CHANGE_SPEC.md` §5 / `05_data_pipeline.md`. Edited manually; `plutus-main.service` reload required after edits.

#### `data/reddit.py` [CHECKED-IN]
Reddit scraper via PRAW.
- `get_reddit_sentiment(symbol, days=7) -> Dict` — scans `IndianStreetBets`, `IndiaInvestments`, `Zerodha`. Returns `{mention_count, score, sample_titles}`.

#### `data/smart_money.py` [CHECKED-IN]
Mutual fund + FII/DII + bulk-deals signal extractor.
- `get_mf_signal(symbol) -> Dict` (verdict ∈ `accumulating | reducing | neutral`)
- `get_fii_dii_flow() -> Dict`
- `get_bulk_deals(symbol) -> List[Dict]`

#### `data/nse_holidays.txt` [CHECKED-IN] — NEW
One ISO date per line. Seeded with NSE 2026 holidays. Refreshed yearly. Consumed by `nse_trading_days_between(start, end)` in the outcome tracker (`backtesting/paper_trader.py` or a small helper). If file missing → fall back to weekdays-only with a logged warning.

#### `data/fno_ban_list.txt` [AUTO]
Daily-refreshed F&O ban list (one symbol per line). Refreshed best-effort from `https://www.nseindia.com/api/liveEquity-derivatives?index=fno_ban_list_active` on first universe screen of the day.

#### `data/.cache/` [AUTO]
Runtime caches: `universe_<weekof>.json`, OHLCV parquet snapshots, etc. Gitignored.

---

### `plutus/strategies/`

5 peer bundles (Composite is a peer, not a meta-filter). All emit `BundleResult` from `base.py`.

#### `strategies/__init__.py` [CHECKED-IN]
Empty.

#### `strategies/base.py` [CHECKED-IN]
`BaseStrategy(bt.Strategy)`. Common indicator helpers (SMA/EMA, RSI, MACD, Bollinger, ATR, Volume ratio), trade-logging hooks, position-sizing utility.

#### `strategies/bundle_trend.py` [CHECKED-IN]
Bundle 1 — Trend Following. EMA 9/21/50 crossover + RSI momentum + volume confirmation; HH/HL structure detection.

#### `strategies/bundle_reversal.py` [CHECKED-IN]
Bundle 2 — Mean Reversion. Bollinger squeeze + RSI extremes + MACD divergence + reversal candlesticks.

#### `strategies/bundle_breakout.py` [CHECKED-IN]
Bundle 3 — Breakout. ATR squeeze + volume breakout + opening-range (9:15–9:30) + Fibonacci levels.

#### `strategies/bundle_smc.py` [CHECKED-IN]
Bundle 4 — Smart Money Concepts. FVG detection, order blocks, liquidity grabs, supply/demand zones.

#### `strategies/bundle_composite.py` [CHECKED-IN]
Bundle 5 — Composite peer. Trades only when 3-of-4 of the other bundles agree on the same bar; from the runner's view it returns its own `BundleResult` like any other bundle. `run_all_bundles()` returns a `Dict[bundle_name, BundleResult]` with **5 keys**.

---

### `plutus/backtesting/`

#### `backtesting/__init__.py` [CHECKED-IN]
Empty.

#### `backtesting/runner.py` [CHECKED-IN]
Backtrader-driven runner.
- `run_all_bundles(symbol, days=90) -> Dict[str, BundleResult]` — 5 keys.
- `run_universe_screen(symbols) -> Dict[symbol, Dict[bundle_name, BundleResult]]`
- `select_best_bundles(results) -> List[str]` — top 2 of 5.

#### `backtesting/paper_trader.py` [CHECKED-IN]
Paper trading + outcome tracking.
- `PaperTrader(portfolio_id)` with `buy/sell/get_positions/get_portfolio_summary`.
- `calc_position_size(...)` — risk-based; unchanged math.
- `track_recommendation_outcomes()` — IST trading-day-aware; uses `entry_mid` as fill, `nse_trading_days_between` for elapsed days, conservative stop-first ambiguity rule, splits `hold_days_min`/`hold_days_max`. See `_CHANGE_SPEC.md` §8.

---

### `plutus/agents/`

#### `agents/__init__.py` [CHECKED-IN]
Empty.

#### `agents/openrouter_client.py` [CHECKED-IN]
OpenAI-compatible OpenRouter client.
- `call_llm(messages, model, response_format=None) -> str`
- Models read from config: `DEEPSEEK_FAST_MODEL` and `DEEPSEEK_REASON_MODEL` (both default to `deepseek/deepseek-v4-flash`).

#### `agents/prompts.py` [CHECKED-IN]
All system prompts as constants: `TECHNICAL_ANALYST_PROMPT`, `SENTIMENT_ANALYST_PROMPT`, `SMART_MONEY_PROMPT`, `RISK_MANAGER_PROMPT`, `SYNTHESIZER_PROMPT`. Synthesizer prompt requires `hold_days_min` and `hold_days_max` in its JSON output.

#### `agents/technical.py` [CHECKED-IN]
Technical Analyst node. Input: OHLCV + indicator dict. Output: `{score, verdict, patterns, entry_zone, targets, stop}`.

#### `agents/sentiment.py` [CHECKED-IN]
Sentiment Analyst node. Input: news + Reddit. Output: `{score, verdict, summary, material_event}`.

#### `agents/smart_money.py` [CHECKED-IN]
Smart Money node. Input: MF holdings deltas + FII/DII flows + bulk deals. Output: `{verdict, mf_count, fii_signal, confidence}`.

#### `agents/risk_manager.py` [CHECKED-IN]
Risk Manager node. Input: entry, stop, capital, open positions. Output: `{shares, capital_used, max_loss, rr_ratio, verdict}`.

#### `agents/synthesizer.py` [CHECKED-IN]
Final synthesizer. Uses `DEEPSEEK_REASON_MODEL`. Output: full `RecommendationDict` including `hold_days_min`, `hold_days_max`, `entry_mid`.

#### `agents/graph.py` [CHECKED-IN]
LangGraph `StateGraph` topology — runs **Technical, Sentiment, SmartMoney in parallel → RiskManager → Synthesizer** sequentially. Entry point:
- `run_analysis(symbol, exchange="NSE") -> RecommendationDict` where the dict includes `hold_days_min`, `hold_days_max`, `entry_mid` (plus all existing fields).

---

### `plutus/alerts/`

#### `alerts/__init__.py` [CHECKED-IN]
Empty.

#### `alerts/telegram_bot.py` [CHECKED-IN]
Builds the python-telegram-bot Application **and** exposes the loopback HTTP routes consumed by `bot.py`.
- `build_telegram_app() -> Application` — wires command handlers (`/start`, `/health`, `/signals`, `/stock`, `/portfolio`, `/buy`, `/sell`, `/watch`, `/history`, `/backtest`, `/confirm`, `/cancel`).
- `register_internal_routes(app: FastAPI) -> None` — registers `POST /push/weekly-summary` and `POST /push/news-alert` on the loopback FastAPI instance owned by `bot.py`.
- Push helpers: `push_weekly_summary(run_id)`, `push_news_alert(event_id)`.
- Pending-trade store (in-memory dict keyed by `user_id + uuid`) for the `/buy → /confirm` flow.

#### `alerts/whatsapp.py` [CHECKED-IN]
CallMeBot WhatsApp pusher. `send_whatsapp(message)` — single HTTP GET to CallMeBot.

---

### `plutus/api/`

#### `api/__init__.py` [CHECKED-IN]
Empty.

#### `api/routes.py` [CHECKED-IN]
FastAPI router with **3 routes**:
- `POST /analyze` — full agent run for `(symbol, exchange)`. Wrapped by the cache + rate limiter from `api/cache.py`.
- `GET /weekly` — latest `weekly_runs` row + its recommendations.
- `GET /health` — liveness check (DB ping + scheduler heartbeat).

Auth: `X-API-Key` header. Responses include `cache_hit: bool` and the `X-RateLimit-Remaining` header.

#### `api/cache.py` [CHECKED-IN] — NEW
In-memory **5-minute symbol cache** plus slowapi rate-limiter wiring.
- `CACHE: Dict[Tuple[str, str], Tuple[float, Dict]]` — key `(symbol.upper(), exchange.upper())`, value `(timestamp, response_dict)`.
- `run_analysis_cached(symbol, exchange) -> Dict` — checks TTL, populates `cache_hit`.
- `limiter = Limiter(key_func=lambda req: req.headers.get("X-API-Key", get_remote_address(req)))`
- Decorator `@limiter.limit("30/hour")` applied to `/analyze`. On 429 returns `{"error": "rate_limit_exceeded", "retry_after_seconds": <n>}`.

---

### `plutus/db/`

#### `db/__init__.py` [CHECKED-IN]
Empty.

#### `db/models.py` [CHECKED-IN]
SQLAlchemy ORM models: `WeeklyRun`, `Recommendation` (with `entry_mid`, `hold_days_min`, `hold_days_max`, `outcome_fill_price`, `outcome_exit_price`, `outcome_exit_date`, `revalidation_note`, `revalidated_at`), `MockPortfolio`, `PaperTrade`, `MaterialEvent`, `RejectedHeadline`, `Watchlist`. See `04_database.md` for full schema.

#### `db/session.py` [CHECKED-IN]
SQLAlchemy `engine`, `SessionLocal`, FastAPI `get_db()` dependency.

#### `db/schema.sql` [CHECKED-IN]
Raw DDL kept in sync with `models.py` (used by `init_db.py` and as a reference for migrations).

#### `db/init_db.py` [CHECKED-IN]
Run-once script: `python -m plutus.db.init_db` creates all tables.

---

### `src/scripts/`

#### `scripts/refresh_seed_universe.py` [CHECKED-IN] — NEW
Manual run only. Pulls the latest Nifty 500 + Nifty MidCap 150 CSVs from NSE, dedupes, writes `plutus/data/seed_universe.csv`. Not invoked by the scheduler.

---

### `src/reports/`

#### `reports/weekly/` [AUTO]
`YYYY-MM-DD.md` per Sunday weekly run. Gitignored. No auto-commit logic — if the user wants history they can `git init` `reports/` separately.

---

### `README.md` [CHECKED-IN]
Project root README — quick start, service map, links into `specs/`.

---

## File Size Estimates

| File | Approx Lines |
|---|---|
| `src/main.py` | ~180 |
| `src/bot.py` | ~120 |
| `src/dashboard.py` | ~650 |
| `plutus/config.py` | ~80 |
| `plutus/data/universe.py` | ~140 |
| `plutus/data/ohlcv.py` | ~100 |
| `plutus/data/news.py` | ~220 |
| `plutus/data/reddit.py` | ~120 |
| `plutus/data/smart_money.py` | ~200 |
| `plutus/strategies/base.py` | ~150 |
| `plutus/strategies/bundle_*.py` | ~150 each |
| `plutus/backtesting/runner.py` | ~200 |
| `plutus/backtesting/paper_trader.py` | ~260 |
| `plutus/agents/graph.py` | ~120 |
| `plutus/agents/*.py` (each node) | ~80–120 each |
| `plutus/agents/prompts.py` | ~220 |
| `plutus/alerts/telegram_bot.py` | ~420 |
| `plutus/api/routes.py` | ~110 |
| `plutus/api/cache.py` | ~60 |
| `plutus/db/models.py` | ~200 |
| `scripts/refresh_seed_universe.py` | ~80 |

---

## `.gitignore` Content (`src/.gitignore`)

```gitignore
.env
.venv/
__pycache__/
*.pyc
*.pyo
reports/
plutus/data/.cache/
*.db
.DS_Store
```

---

## Python Version

Use **Python 3.11** (not 3.12+). LangGraph 0.2.x has best support on 3.11.
On OCI ARM64 Ubuntu 22.04: `sudo apt install python3.11 python3.11-venv python3.11-dev`.

Run entry points as modules so package-relative imports work:

```bash
cd /home/ubuntu/plutus-app/src
python -m main          # plutus-main.service
python -m bot           # plutus-bot.service
streamlit run dashboard.py --server.port 8501
```
