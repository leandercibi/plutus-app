# 01 — Build Sequencing

> This file tells the implementing agent exactly what to build, in what order,
> and what each phase depends on. Follow phases strictly — later phases import from earlier ones.

---

## Phase Map

```
Phase 1  →  Phase 2  →  Phase 3  →  Phase 4  →  Phase 5  →  Phase 6  →  Phase 7  →  Phase 8  →  Phase 9
Config      Database    Data        Strategies  Agents      API +       Dashboard   Reddit +    Deployment
+ Env       Schema      Pipeline    + Backtest  (LLM)       Scheduler   (Streamlit) MF/FII +    (OCI)
+ Seeds                 (5 bundles)             (V4 Flash)  + Bot                   WhatsApp
                                                            (split)
```

---

## Phase 1: Project Bootstrap

**Goal:** Working skeleton. Imports don't fail. Config loads from env. Static seed files in place.

### Steps
1. Create `plutus-app/` directory at `/Users/leander/personal-projects/plutus-app/` with `src/` as the code root
2. Create the top-level Python package at `src/plutus/` (with `__init__.py`)
3. Create Python virtual environment: `python3.11 -m venv .venv`
4. Install dependencies from `src/requirements.txt` (see `03_config_env.md`)
5. Create `src/plutus/config.py` (see `03_config_env.md` for full implementation)
6. Create `src/.env` file with placeholder values
7. Create the seed universe CSV at `src/plutus/data/seed_universe.csv` with columns `symbol,exchange,segment` (segment ∈ `LARGE_CAP`, `MID_CAP`). Seed it with Nifty 500 + Nifty MidCap 150 constituents (~650 unique symbols, refreshed manually monthly from NSE).
8. Create the material-event keyword file at `src/plutus/data/material_keywords.yaml` (tier_A / tier_B / tier_C + stoplist — see `_CHANGE_SPEC.md` §5 for the canonical content).
9. Create the NSE holidays file at `src/plutus/data/nse_holidays.txt` (one ISO date per line; seed with 2026 NSE holidays).
10. Verify: `python -c "from plutus.config import settings; print(settings.OPENROUTER_API_KEY[:4])"` prints first 4 chars.

### Produces
- `src/plutus/__init__.py`
- `src/plutus/config.py`
- `src/plutus/data/seed_universe.csv`
- `src/plutus/data/material_keywords.yaml`
- `src/plutus/data/nse_holidays.txt`
- `src/.env`
- `src/requirements.txt`
- `src/.gitignore` (must exclude `.env` and `reports/weekly/`)

---

## Phase 2: Database

**Goal:** PostgreSQL schema created, SQLAlchemy models working, session factory ready.

**Depends on:** Phase 1 (config for DB URL)

### Steps
1. Ensure PostgreSQL 16 is running (see `15_deployment.md` for OCI install)
2. Create database: `createdb plutus_db`
3. Implement `src/plutus/db/session.py` — SQLAlchemy engine + SessionLocal factory
4. Implement `src/plutus/db/models.py` — all ORM models (see `04_database.md`)
5. Run `python -m plutus.db.init_db` to create all tables via `Base.metadata.create_all()`
6. Apply additive ALTERs on `recommendations` (see SQL below) — these add the entry-mid / hold-window / outcome-fill columns the new outcome tracker needs.
7. Verify: `python -m plutus.db.init_db` → "All tables created." printed

### Produces
- `src/plutus/db/session.py`
- `src/plutus/db/models.py`
- `src/plutus/db/init_db.py`

### Tables Created
- `weekly_runs`, `recommendations`, `mock_portfolios`, `paper_trades`,
  `watchlist`, `news_events`, `backtest_results`, `rejected_headlines`

### Required ALTERs on `recommendations`

```sql
ALTER TABLE recommendations ADD COLUMN entry_mid NUMERIC(12, 2);
ALTER TABLE recommendations ADD COLUMN hold_days_min INTEGER;
ALTER TABLE recommendations ADD COLUMN hold_days_max INTEGER;
ALTER TABLE recommendations ADD COLUMN outcome_fill_price NUMERIC(12, 2);
ALTER TABLE recommendations ADD COLUMN outcome_exit_price NUMERIC(12, 2);
ALTER TABLE recommendations ADD COLUMN outcome_exit_date DATE;
ALTER TABLE recommendations ADD COLUMN revalidation_note VARCHAR(200);
ALTER TABLE recommendations ADD COLUMN revalidated_at TIMESTAMP;
```

### `rejected_headlines` table

```sql
CREATE TABLE rejected_headlines (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    headline TEXT NOT NULL,
    source VARCHAR(50),
    published_at TIMESTAMP,
    filter_status VARCHAR(20),  -- 'stoplist' | 'no_keyword'
    rejected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_rejected_symbol_at ON rejected_headlines (symbol, rejected_at DESC);
```

---

## Phase 3: Data Pipeline

**Goal:** Can fetch the curated stock universe, OHLCV data, news (with prefilter), and prepare inputs for strategies.

**Depends on:** Phase 1 (config + seed files), Phase 2 (DB for caching + `rejected_headlines`)

### Steps
1. Implement `src/plutus/data/universe.py` — loads `seed_universe.csv`, applies OHLCV-derived liquidity filters (price band, 30d avg volume, 30d avg traded value), applies F&O ban filter from `data/fno_ban_list.txt`, caches result to `data/.cache/universe_<weekof>.json` (see `05_data_pipeline.md` and `_CHANGE_SPEC.md` §2)
2. Implement `src/plutus/data/ohlcv.py` — fetch historical OHLCV via yfinance + `fetch_live_price` for the Monday revalidation job
3. Implement `src/plutus/data/news.py` — NewsAPI + RSS headline fetcher; `prefilter_headlines()` against `material_keywords.yaml`; `save_rejected_headlines()` writes to the `rejected_headlines` table; `_llm_batch_classify()` calls the LLM once per symbol with all kept headlines
4. Implement `src/plutus/data/reddit.py` — PRAW scraper for r/IndianStreetBets
5. Implement `src/plutus/data/smart_money.py` — AMFI MF data + NSE FII/DII scraper

### Verification Commands
```bash
python -c "from plutus.data.universe import get_universe; u = get_universe(); print(f'{len(u)} stocks')"
# Expected: 150-200 stocks after liquidity + F&O ban filters

python -c "from plutus.data.ohlcv import fetch_ohlcv; df = fetch_ohlcv('RELIANCE', days=90); print(df.tail())"
# Expected: DataFrame with 90 rows of OHLCV

python -c "from plutus.data.news import fetch_news, prefilter_headlines; hs = fetch_news('RELIANCE'); print(len(hs), len(prefilter_headlines(hs)))"
# Expected: total fetched count, then a smaller prefiltered count
```

### Build Order Within Phase
1. `universe.py` first (strategies need the ticker list)
2. `ohlcv.py` second (strategies need OHLCV data)
3. `news.py` third (agents need news + prefilter writes to `rejected_headlines`)
4. `reddit.py` fourth (agents need sentiment)
5. `smart_money.py` last (agents need MF/FII data)

---

## Phase 4: Strategies + Backtesting

**Goal:** All **5 peer strategy bundles** implemented (Composite is a peer, not a meta-filter). Backtest runner works. Paper trading works.

**Depends on:** Phase 3 (OHLCV data), Phase 2 (DB for results)

### Steps
1. Implement `src/plutus/strategies/base.py` — shared base class
2. Implement `src/plutus/strategies/bundle_trend.py`
3. Implement `src/plutus/strategies/bundle_reversal.py`
4. Implement `src/plutus/strategies/bundle_breakout.py`
5. Implement `src/plutus/strategies/bundle_smc.py`
6. Implement `src/plutus/strategies/bundle_composite.py` — runs as a peer; its internal rule is "trade only when 3-of-4 of the other bundles agree on the same bar," but `run_all_bundles()` returns it alongside the other four
7. Implement `src/plutus/backtesting/runner.py` — runs all 5 bundles, returns `Dict[bundle_name, BundleResult]` (5 keys), and exposes "top 2 of 5" ranking
8. Implement `src/plutus/backtesting/paper_trader.py` — mock trade execution + P&L tracking

### Verification Commands
```bash
python -m plutus.backtesting.runner --symbol RELIANCE --days 90
# Expected: Table of 5 bundles with win_rate, sharpe, avg_return

python -c "
from plutus.backtesting.paper_trader import PaperTrader
pt = PaperTrader(portfolio_id=1)
pt.buy('RELIANCE', price=2389.50, shares=42)
print(pt.get_positions())
"
# Expected: dict with RELIANCE position
```

---

## Phase 5: LangGraph Agents

**Goal:** Full DeepSeek-powered agent pipeline runs for a single stock and returns structured recommendation. Synthesizer outputs `hold_days_min` / `hold_days_max` and entry zone (so `entry_mid` can be computed before insert).

**Depends on:** Phase 3 (data), Phase 4 (backtest scores from 5 bundles as input)

### Model

Both the fast agents and the synthesizer point to **DeepSeek V4 Flash**:

```python
# src/plutus/config.py
DEEPSEEK_FAST_MODEL: str = "deepseek/deepseek-v4-flash"     # all fast agents
DEEPSEEK_REASON_MODEL: str = "deepseek/deepseek-v4-flash"   # synthesizer
```

The two env vars stay separate so a heavier reasoner can be swapped in later by changing one variable.

### Steps
1. Set up OpenRouter client in `src/plutus/agents/openrouter_client.py`
2. Implement `src/plutus/agents/prompts.py` — all system prompts; the synthesizer prompt must produce `hold_days_min` and `hold_days_max` (e.g., "5–8" → min=5, max=8)
3. Implement `src/plutus/agents/technical.py` — Technical Analyst node (V4 Flash)
4. Implement `src/plutus/agents/sentiment.py` — Sentiment node (V4 Flash; consumes prefiltered + batched news)
5. Implement `src/plutus/agents/smart_money.py` — Smart Money node (V4 Flash)
6. Implement `src/plutus/agents/risk_manager.py` — Risk Manager node (V4 Flash)
7. Implement `src/plutus/agents/synthesizer.py` — Synthesizer node (V4 Flash)
8. Implement `src/plutus/agents/graph.py` — LangGraph StateGraph wiring all nodes; `run_analysis()` populates `entry_mid = (entry_low + entry_high) / 2` before insert

### Verification Command
```bash
python -c "
from plutus.agents.graph import run_analysis
result = run_analysis('RELIANCE')
print(result['recommendation'], result['confidence'], result['hold_days_min'], result['hold_days_max'])
"
# Expected: e.g. "BUY 7.5 5 8" printed after ~20 seconds
```

---

## Phase 6: API + Scheduler + Telegram Bot (split processes)

**Goal:** Two long-lived Python processes:
- `plutus-main` — FastAPI on port 8000 + APScheduler (5 jobs).
- `plutus-bot` — Telegram polling + an internal-only FastAPI receiver on `127.0.0.1:8001` for push commands.

**Depends on:** Phase 5 (agents), Phase 4 (backtesting), Phase 2 (DB)

### Steps
1. Implement `src/plutus/api/routes.py` — FastAPI routes: `/analyze`, `/health`, weekly run trigger. `/analyze` enforces 30/hr per-API-key rate limit (slowapi) and a 5-minute symbol-level in-memory cache (returns `cache_hit: bool` and `X-RateLimit-Remaining` header).
2. Implement `src/plutus/alerts/telegram_bot.py` exposing:
   - `build_telegram_app() -> Application` (python-telegram-bot)
   - `register_internal_routes(app: FastAPI)` — registers `POST /push/weekly-summary` and `POST /push/news-alert` on the bot's local FastAPI app
   - command handlers: `cmd_health`, `cmd_stock`, `cmd_portfolio`, `cmd_buy`, `cmd_sell`, `cmd_confirm`, `cmd_cancel` (with the literal-shares + risk-warning + 60-second `/confirm` flow)
   - push functions: `push_weekly_summary(run_id)`, `push_news_alert(event_id)`
3. Implement `src/plutus/alerts/whatsapp.py` — CallMeBot push
4. Implement `src/main.py` (entry point for `plutus-main.service`):
   - boots FastAPI on `:8000` (mounts `plutus.api.routes`)
   - boots APScheduler with **five** jobs: `weekly_pipeline` (Sun 18:00 IST), `weekly_revalidate` (Mon 09:10 IST), `news_monitor` (Mon–Fri hourly 09:00–15:59 IST), `outcome_tracker` (Mon–Fri 16:30 IST), `rejected_headlines_cleanup` (daily 03:00 IST, deletes rows older than 30d)
   - does **not** import or start the Telegram bot
   - when it needs to push to the bot it calls `http://127.0.0.1:8001/push/...` via `httpx`; if the bot is down it logs a warning and continues
5. Implement `src/bot.py` (entry point for `plutus-bot.service`):
   - boots a local-only FastAPI app on `127.0.0.1:8001` and calls `register_internal_routes(app)`
   - boots `build_telegram_app().run_polling()` in the same event loop
   - reads the DB directly for command handlers; calls `plutus-main`'s `/analyze` for `/stock SYMBOL` (so it goes through the rate limit + cache)
6. Implement `weekly_pipeline()` in `src/plutus/jobs/weekly.py` (or `main.py`) — full Sunday research run; on success calls the bot's push endpoint
7. Implement `weekly_revalidate()` — Monday gap re-validation. For each `BUY`/`WATCH` rec from the latest run, fetches LTP via `data.ohlcv.fetch_live_price`; if `LTP > entry_high * 1.02` → BUY → WATCH; if `LTP < stop_loss` → BUY → AVOID. Writes `revalidation_note` + `revalidated_at`. Sends one Telegram delta. **No LLM calls.**
8. Implement `news_monitor()` — hourly news scan over watchlist + open positions; uses `prefilter_headlines` then `_llm_batch_classify` per symbol; pushes alerts via `POST /push/news-alert`
9. Implement `outcome_tracker()` per the patched algorithm in `_CHANGE_SPEC.md` §8: IST trading-day boundaries via `nse_trading_days_between` (uses `data/nse_holidays.txt`), fill = `entry_mid`, conservative same-bar collision rule (stop wins), `EXPIRED` only after `hold_days_max`. Persists `outcome_fill_price`, `outcome_exit_price`, `outcome_exit_date`.
10. Implement `rejected_headlines_cleanup()` — `DELETE FROM rejected_headlines WHERE rejected_at < now() - interval '30 days'`.

### Verification
```bash
# Start the main process
python -m src.main &

# Start the bot process
python -m src.bot &

# Test API
curl -X POST http://localhost:8000/analyze \
  -H "X-API-Key: your_key" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "INFY"}'
# Expected: JSON with recommendation, cache_hit=false, X-RateLimit-Remaining header

# Repeat within 5 minutes → cache_hit=true
curl -X POST http://localhost:8000/analyze \
  -H "X-API-Key: your_key" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "INFY"}' | jq .cache_hit
# Expected: true

# Test bot internal push (loopback only)
curl -X POST http://127.0.0.1:8001/push/weekly-summary \
  -H "Content-Type: application/json" \
  -d '{"run_id": 1}'
# Expected: 200 OK; bot sends Telegram message

# Test Telegram (send message from phone)
# /health → bot replies "✅ Plutus is running"
# /stock RELIANCE → bot replies with analysis after ~20sec (goes through /analyze cache)
```

---

## Phase 7: Dashboard

**Goal:** Streamlit dashboard running on port 8501 with all **8 tabs** populated with live data. Settings is a tab, not a sidebar.

**Depends on:** All previous phases (reads from PostgreSQL)

### Tabs (in order)
1. **Home** — top-level KPIs, latest weekly run summary
2. **Signals** — current BUY / WATCH / AVOID recommendations
3. **Portfolio** — mock portfolios + paper trades + open positions + P&L
4. **Strategy Lab** — per-bundle backtest results across the 5 bundles
5. **News Feed** — two sub-sections:
   - "Material Events (last 7d)" — alerts that fired
   - "Rejected Headlines (last 7d)" — table from `rejected_headlines` with columns `time | symbol | headline | source | filter_status`, search box, and a "Promote keyword" UX nudge that prints a copy-paste hint for `material_keywords.yaml` (no auto-edit)
6. **Watchlist** — user watchlist CRUD
7. **History** — full per-week drilldown from `weekly_runs`; clicking a row shows the markdown body of `reports/weekly/<date>.md` (if present), the recommendations table for that run, an outcome summary (HIT_T1 / HIT_T2 / STOPPED / EXPIRED / PENDING counts), and an equity curve overlay vs Nifty50
8. **Settings** — env-driven toggles, model identifiers, advisory thresholds (rendered as a tab, not a sidebar)

### Steps
1. Implement `src/dashboard.py` — all 8 tabs (see `11_dashboard.md`)
2. Test each tab loads without error with sample data in DB
3. Verify Portfolio tab shows mock portfolios and News Feed → Rejected Headlines sub-section reads from `rejected_headlines`

### Verification
```bash
streamlit run src/dashboard.py --server.port 8501 --server.address 0.0.0.0
# Open http://localhost:8501 — all 8 tabs visible (Home, Signals, Portfolio,
# Strategy Lab, News Feed, Watchlist, History, Settings)
```

---

## Phase 8: Reddit + MF/FII + WhatsApp

**Goal:** Full sentiment pipeline working. WhatsApp alerts firing.

**Depends on:** Phase 6 (alerts infrastructure)

### Steps
1. Wire `plutus.data.reddit` into `plutus.agents.sentiment`
2. Wire `plutus.data.smart_money` into `plutus.agents.smart_money`
3. Test `plutus.alerts.whatsapp` sends a test message
4. Integrate CallMeBot into the `news_monitor` alert path

---

## Phase 9: Deployment (OCI)

**Goal:** All processes running as systemd services. Dashboard accessible via Cloudflare tunnel.

**See:** `15_deployment.md` for exact commands.

### systemd services (4 total)

| Service | Process | What it runs |
|---|---|---|
| `postgresql.service` | system-managed | PostgreSQL 16 (unchanged) |
| `plutus-main.service` | `python -m src.main` | FastAPI on `:8000` + APScheduler (5 jobs) |
| `plutus-bot.service` | `python -m src.bot` | Telegram polling + internal FastAPI on `127.0.0.1:8001` |
| `plutus-dashboard.service` | `streamlit run src/dashboard.py --server.port 8501` | Streamlit dashboard |

Deploy path on OCI: `/home/ubuntu/plutus-app/`. Service unit files live in `/etc/systemd/system/plutus-*.service`.

---

## Dependency Graph (Module Imports)

```
plutus/config.py
  └── plutus/db/session.py
        └── plutus/db/models.py
              └── plutus/db/init_db.py

plutus/data/universe.py     ←── plutus/config.py, plutus/data/seed_universe.csv
plutus/data/ohlcv.py        ←── plutus/config.py
plutus/data/news.py         ←── plutus/config.py, plutus/data/material_keywords.yaml,
                                plutus/db/models.py (rejected_headlines)
plutus/data/reddit.py       ←── plutus/config.py
plutus/data/smart_money.py  ←── plutus/config.py

plutus/strategies/base.py        ←── (no project imports)
plutus/strategies/bundle_*.py    ←── plutus/strategies/base.py, plutus/data/ohlcv.py
plutus/strategies/bundle_composite.py ←── plutus/strategies/base.py,
                                          plutus/strategies/bundle_trend.py,
                                          plutus/strategies/bundle_reversal.py,
                                          plutus/strategies/bundle_breakout.py,
                                          plutus/strategies/bundle_smc.py

plutus/backtesting/runner.py        ←── plutus/strategies/* (5 bundles), plutus/data/ohlcv.py,
                                        plutus/db/models.py
plutus/backtesting/paper_trader.py  ←── plutus/db/models.py, plutus/db/session.py

plutus/agents/openrouter_client.py  ←── plutus/config.py
plutus/agents/prompts.py            ←── (no imports)
plutus/agents/technical.py          ←── plutus/agents/openrouter_client.py, plutus/agents/prompts.py
plutus/agents/sentiment.py          ←── plutus/agents/openrouter_client.py,
                                        plutus/data/news.py, plutus/data/reddit.py
plutus/agents/smart_money.py        ←── plutus/agents/openrouter_client.py, plutus/data/smart_money.py
plutus/agents/risk_manager.py       ←── plutus/agents/openrouter_client.py, plutus/config.py
plutus/agents/synthesizer.py        ←── plutus/agents/openrouter_client.py, plutus/agents/prompts.py
plutus/agents/graph.py              ←── ALL agent nodes, plutus/backtesting/runner.py, plutus/data/*

plutus/api/routes.py                ←── plutus/agents/graph.py, plutus/db/models.py, plutus/config.py
plutus/alerts/telegram_bot.py       ←── plutus/agents/graph.py, plutus/db/models.py,
                                        plutus/backtesting/paper_trader.py
plutus/alerts/whatsapp.py           ←── plutus/config.py

plutus/jobs/weekly.py               ←── plutus/agents/graph.py, plutus/data/*, plutus/db/*
plutus/jobs/revalidate.py           ←── plutus/data/ohlcv.py, plutus/db/*
plutus/jobs/news_monitor.py         ←── plutus/data/news.py, plutus/alerts/*, plutus/db/*
plutus/jobs/outcome_tracker.py      ←── plutus/data/ohlcv.py, plutus/db/*
plutus/jobs/cleanup.py              ←── plutus/db/*

src/main.py   (entry point: plutus-main)
              ←── plutus/api/routes.py, plutus/jobs/* (APScheduler), httpx (push to bot)
              # Does NOT import plutus/alerts/telegram_bot.py.

src/bot.py    (entry point: plutus-bot)
              ←── plutus/alerts/telegram_bot.py
              # Boots Telegram polling + local FastAPI on 127.0.0.1:8001 for push receivers.
              # Calls main's /analyze over HTTP for /stock command.

src/dashboard.py
              ←── plutus/db/session.py, plutus/db/models.py, plutus/config.py
```

---

## What NOT to Build (Out of Scope for MVP)

- Real trade execution (paper trading only in MVP; the system never places live orders)
- Scalping strategies (requires tick data, not worth it at ₹1L capital)
- Elliott Wave detection (too subjective to automate reliably)
- Email reports
- Multi-user support (single user system)
- Docker (unnecessary complexity for single-user OCI deployment)
- Redis (no pub/sub needed; APScheduler handles scheduling in-process)
