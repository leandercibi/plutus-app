# Plutus — Consolidated Change Specification (v2)

> **Authoritative source for the spec rewrite.** Every spec file under `personal-projects/plutus-app/specs/`
> must be rewritten to comply with the decisions below. Do not introduce decisions not listed here.
> If a decision conflicts with the existing spec, this document wins.

Date locked: 2026-05-30
Owner: Leander
Drives: PRD.md + `01_sequencing.md` … `15_deployment.md`

---

## 0. Project naming & layout

| Item | New value |
|---|---|
| Project name (canonical) | **Plutus** (display name: "Plutus — Indian Equities Recommendation Engine") |
| Repo root | `/Users/leander/personal-projects/plutus-app/` |
| Code root | `/Users/leander/personal-projects/plutus-app/src/` |
| Top-level Python package | `plutus` (so `from plutus.data.universe import ...`) |
| Database | `plutus_db` (unchanged) |
| Database user | `plutus` (unchanged) |
| Systemd unit prefix | `plutus-*` (e.g. `plutus-main.service`, `plutus-bot.service`, `plutus-dashboard.service`) |
| OCI deploy path | `/home/ubuntu/plutus-app/` |
| Specs path | `/Users/leander/personal-projects/plutus-app/specs/` |
| Reports path | `/Users/leander/personal-projects/plutus-app/src/reports/weekly/` |

**Every reference to "indiatradeai" anywhere in any spec file must become "plutus".**
**Every reference to `/home/ubuntu/indiatradeai` becomes `/home/ubuntu/plutus-app`.**
**Every reference to `/Users/leander/projects/indiatradeai` becomes `/Users/leander/personal-projects/plutus-app/src`.**

Code module structure (under `src/`):

```
src/
├── plutus/                 # main Python package
│   ├── __init__.py
│   ├── config.py
│   ├── data/
│   ├── strategies/
│   ├── backtesting/
│   ├── agents/
│   ├── alerts/
│   ├── api/
│   └── db/
├── main.py                 # entry point for plutus-main service (FastAPI + scheduler)
├── bot.py                  # entry point for plutus-bot service (Telegram, separate process)
├── dashboard.py            # entry point for plutus-dashboard (Streamlit)
├── reports/
│   └── weekly/             # YYYY-MM-DD.md per weekly run; gitignored
├── requirements.txt
└── .env                    # gitignored
```

`reports/weekly/` is **`.gitignore`d** (Q14 = option a). No auto-commit logic in the system. User can `git init` `reports/` separately if they want history; system does not manage that.

---

## 1. Strategy bundles — 5 total

Decision: **5 strategy bundles**, all peers, all run independently.

| # | Bundle | Module |
|---|---|---|
| 1 | Trend | `plutus/strategies/bundle_trend.py` |
| 2 | Reversal | `plutus/strategies/bundle_reversal.py` |
| 3 | Breakout | `plutus/strategies/bundle_breakout.py` |
| 4 | SMC (Smart Money Concepts) | `plutus/strategies/bundle_smc.py` |
| 5 | Composite | `plutus/strategies/bundle_composite.py` |

**Composite is a peer bundle, not a meta-filter.** It runs its own backtest and produces its own trades. Its internal logic is "trade only when 3-of-4 of the other bundles agree on the same bar," but from the runner's perspective it's just another bundle with `run_all_bundles()` returning 5 results.

Anywhere the spec says "4 bundles" → change to "5 bundles". Anywhere it says "top 2 of 4" → "top 2 of 5". The runner returns `Dict[bundle_name, BundleResult]` with 5 keys.

---

## 2. Universe screener — Nifty 500 + MidCap 150 seed list

Decision: **No `yfinance.Ticker.info` calls for screening.** Use a static curated seed list.

### `data/universe.py` rewritten contract

1. Load `data/seed_universe.csv` — a checked-in CSV with columns: `symbol, exchange, segment` (segment ∈ `LARGE_CAP`, `MID_CAP`).
   - Initial content: Nifty 500 constituents + Nifty MidCap 150 constituents (≈650 unique symbols).
   - Refreshed manually monthly from NSE CSVs at https://www.nseindia.com/products-services/indices-nifty500-index and https://www.nseindia.com/products-services/indices-nifty-midcap-150-index.
   - The system has a helper script `scripts/refresh_seed_universe.py` (manual run) but the seed CSV is the source of truth at runtime.
2. For each symbol, fetch OHLCV (90-day daily) via `data.ohlcv.fetch_ohlcv()` — this is already cached and reused downstream.
3. Apply filters using OHLCV (no `Ticker.info`):
   - `last_close` between `UNIVERSE_PRICE_MIN` (₹50) and `UNIVERSE_PRICE_MAX` (₹5000)
   - `avg_daily_volume_30d` > `UNIVERSE_MIN_AVG_VOLUME` (5,00,000 shares)
   - `avg_traded_value_30d` > `UNIVERSE_MIN_AVG_VALUE_CR` (₹10 Cr) — proxy for liquidity that doesn't need market cap
4. F&O ban filter: load ban list from a static daily-refreshed file `data/fno_ban_list.txt`. If the file is older than 24h, fetch fresh from `https://www.nseindia.com/api/liveEquity-derivatives?index=fno_ban_list_active` (best-effort; if fetch fails, use stale file with a logged warning).
5. Output: `List[str]` of symbols, typically ~150-200 after filters.
6. Cache the filtered universe to `data/.cache/universe_<weekof>.json` so subsequent calls within the same week are free.

**Drop:** Market-cap filter (`UNIVERSE_MIN_MCAP_CR`) — replaced by traded-value proxy. Remove `UNIVERSE_MIN_MCAP_CR` from config.

---

## 3. Position sizing & buy/sell semantics

### `/buy` and `/sell` Telegram commands (Q5)

User provides `shares` directly. Bot does NOT auto-reject. Bot prints a risk-line warning if any of:
- This trade is > 5% of `initial_capital` at risk (i.e. `(price - rec.stop_loss) * shares > 0.05 * initial_capital`)
- Open positions in this portfolio would exceed 4 (advisory only)
- Capital used > available cash (this is hard reject, since the math is just wrong)

Format:

```
⚠️ Pre-trade check:
   Shares: 50 × ₹790 = ₹39,500 (39.5% of capital)
   Risk: ₹1,750 (1.75% — within 5% limit ✓)
   Open positions after: 5 (above advisory limit of 4 ⚠)

Confirm? Reply /confirm or /cancel within 60 seconds.
```

Bot stores the pending trade in memory (not DB) keyed by user ID + a UUID. On `/confirm`, it inserts the `paper_trades` row. On timeout, drops the pending trade.

### `MAX_OPEN_POSITIONS` is advisory (Q6)

Default = 4. User can override in `.env`. Soft warning only; the bot can suggest up to 10 if more candidates are viable. Add new env var:

```
MAX_OPEN_POSITIONS_ADVISORY: int = 4
MAX_OPEN_POSITIONS_HARD: int = 10   # hard cap; truly cannot exceed
```

Backtester `calc_position_size` keeps its risk-based formula unchanged.

---

## 4. Weekly run — Sunday research + Monday re-validation (Q7 = option a)

### Sunday 18:00 IST: full research run (unchanged)

Runs against Friday close. Writes `weekly_runs` + `recommendations` rows. Sends Telegram summary.

### Monday 09:10 IST: re-validation pass (NEW)

A new APScheduler job `weekly_revalidate` runs Monday 09:10 IST (10 minutes after market open) and:

1. For each `recommendation` from the latest `weekly_run` with `recommendation IN ('BUY', 'WATCH')`:
   - Fetch current LTP (via `data.ohlcv.fetch_live_price`).
   - If `LTP > entry_high * 1.02` → downgrade BUY → WATCH (gapped past entry).
   - If `LTP < stop_loss` → downgrade BUY → AVOID (already broken).
   - If no downgrade → recommendation unchanged.
2. Update `recommendations.recommendation` and add `revalidation_note` column.
3. Send a single Telegram delta message: `"📊 Monday open: 1 BUY downgraded (RELIANCE → WATCH, gapped +2.4%)"`.
4. **No LLM calls in this job.** Pure price math.

### New DB columns

```sql
ALTER TABLE recommendations ADD COLUMN revalidation_note VARCHAR(200);
ALTER TABLE recommendations ADD COLUMN revalidated_at TIMESTAMP;
```

---

## 5. News pipeline — hard prefilter + batch classification (Q8, Q9)

### Tiered keyword prefilter (Q9)

Stored in `src/plutus/data/material_keywords.yaml`. Three tiers (A, B, C). Default enabled tiers via env: `MATERIAL_KEYWORD_TIERS=A,B`. (C is in the YAML but not enabled by default.)

**File: `src/plutus/data/material_keywords.yaml`**

```yaml
# Plutus material-event keyword prefilter
# All matches are case-insensitive substring matches.
# Hits in ANY enabled tier → headline is sent to LLM classifier.
# Stoplist matches override tier matches and reject the headline.

tier_A:
  - sebi
  - rbi
  - sfio
  - cbi
  - mca
  - sebi order
  - sebi bars
  - sebi bans
  - sebi penalty
  - debar
  - debarred
  - barred from
  - show cause
  - interim order
  - disgorgement
  - manipulation
  - front-running
  - front running
  - pump and dump
  - pump-and-dump
  - fund diversion
  - market access barred
  - fema
  - irdai
  - usfda
  - us fda
  - fda warning
  - warning letter
  - import alert
  - form 483
  - oai status
  - official action indicated
  - voluntary action indicated
  - vai status
  - eir
  - anda
  - drug approval
  - drug recall
  - gmp violation
  - data integrity
  - q1 result
  - q2 result
  - q3 result
  - q4 result
  - quarterly result
  - qtr result
  - profit jumps
  - profit surges
  - profit doubles
  - profit triples
  - profit falls
  - profit declines
  - loss widens
  - loss narrows
  - loss-making
  - beats estimates
  - misses estimates
  - guidance cut
  - guidance raised
  - guidance lowered
  - ebitda surge
  - ebitda margin
  - revenue surge
  - revenue declines
  - record profit
  - record revenue
  - fy26 result
  - fy27 result
  - supreme court
  - sc rules
  - sc upholds
  - sc verdict
  - sc judgment
  - sc dismisses
  - high court
  - hc ruling
  - hc rules
  - nclt
  - nclat
  - tribunal ruling
  - tribunal order
  - contempt
  - stay order
  - injunction
  - appellate
  - auditor resignation
  - auditor resigns
  - qualified opinion
  - disclaimer of opinion
  - adverse opinion
  - going concern
  - restatement
  - accounting irregularities
  - accounting fraud
  - ceo resigns
  - ceo steps down
  - ceo removed
  - md resigns
  - md steps down
  - cfo resigns
  - chairman resigns
  - chairman steps down
  - whistleblower
  - sfio probe
  - ed raid
  - cbi raid
  - income tax raid
  - it raid
  - it search
  - tariff
  - trade war
  - reciprocal tariff
  - sanctions on india
  - recession warning
  - crude oil surge
  - crude oil crash
  - rupee crash
  - rupee record low
  - rupee plunges
  - acquisition
  - acquires
  - to acquire
  - takeover
  - open offer
  - definitive agreement
  - merger
  - scheme of arrangement
  - demerger
  - hive off
  - hive-off
  - slump sale
  - strategic stake
  - joint venture
  - jv with
  - mou with
  - divestment

tier_B:
  - block deal
  - bulk deal
  - stake offload
  - stake purchase
  - sells stake
  - buys stake
  - acquires stake
  - stake sale
  - ofs
  - offer for sale
  - qip
  - qualified institutional placement
  - promoter pledge
  - pledged shares
  - unpledge
  - promoter stake
  - promoter buying
  - promoter selling
  - promoter holding
  - insider trading
  - related party
  - related-party
  - fii selling
  - fii buying
  - fii outflow
  - fii inflow
  - dii buying
  - dii selling
  - fpi outflow
  - fpi inflow
  - msci rebalance
  - msci inclusion
  - msci exclusion
  - msci weight
  - ftse rebalance
  - index inclusion
  - index exclusion
  - mutual fund accumulating
  - mf buying
  - order win
  - bags order
  - secures order
  - contract awarded
  - contract worth
  - deal worth
  - loa
  - letter of award
  - purchase order
  - contract from
  - signed contract
  - order from ministry
  - order from indian army
  - order from indian navy
  - order from iaf
  - order from railway
  - order from coal india
  - rating downgrade
  - rating upgrade
  - downgraded by
  - upgraded by
  - credit rating
  - moody's
  - "s&p"
  - fitch
  - crisil
  - icra
  - care ratings
  - default
  - npa
  - slippage
  - watch negative
  - gst notice
  - gst demand
  - gst council
  - dggi notice
  - income tax notice
  - tax demand
  - tax raid
  - retrospective tax

tier_C:
  - buyback
  - share buyback
  - special dividend
  - interim dividend
  - bonus issue
  - stock split
  - record date
  - ex-dividend
  - rights issue
  - fpo
  - follow-on
  - preferential allotment
  - ncd issue
  - bond issue
  - fundraise
  - fund raise
  - upper circuit
  - lower circuit
  - asm long term
  - asm framework
  - gsm framework
  - esm framework
  - t2t segment
  - fno ban
  - mwpl breach
  - security in ban
  - new ceo
  - ceo appointed
  - new md
  - md appointed
  - new chairman
  - succession plan

stoplist:
  - "top 5"
  - "top 10"
  - "stocks to buy"
  - "stocks to watch"
  - "tips"
  - "stocks for the week"
  - "penny stock"
  - "multibagger"
  - "sensex live"
  - "nifty live"
  - "market live"
  - "opening bell"
  - "closing bell"
  - "pre-open"
```

### Algorithm in `data/news.py`

```python
def prefilter_headlines(headlines: List[Dict]) -> List[Dict]:
    """Returns subset that pass keyword tier match AND don't hit stoplist."""
    enabled_tiers = settings.MATERIAL_KEYWORD_TIERS.split(",")  # default "A,B"
    keywords = load_keywords(enabled_tiers)   # from yaml
    stoplist = load_stoplist()                # from yaml

    passed = []
    for h in headlines:
        title = h["headline"].lower()
        if any(s in title for s in stoplist):
            h["filter_status"] = "stoplist"
            continue
        if any(k in title for k in keywords):
            h["filter_status"] = "kept"
            passed.append(h)
        else:
            h["filter_status"] = "no_keyword"
    return passed


def classify_news(symbol: str, headlines: List[Dict]) -> Dict:
    kept = prefilter_headlines(headlines)
    if not kept:
        # No LLM call. Persist all rejected with filter_status, return neutral.
        save_rejected_headlines(symbol, [h for h in headlines if h.get("filter_status") in ("stoplist", "no_keyword")])
        return {
            "sentiment_score": 0,
            "sentiment_label": "neutral",
            "is_material": False,
            "material_event_type": None,
            "summary": "No material headlines.",
        }
    # Single batched LLM call across all kept headlines for this symbol.
    return _llm_batch_classify(symbol, kept)
```

### Batched LLM call (Q8)

`_llm_batch_classify` sends ALL kept headlines for a symbol in one call (already in spec). For news_monitor across multiple watchlist symbols, the loop is:

```python
for symbol in watchlist + open_positions:
    classify_news(symbol, fetch_news(symbol))
```

(One LLM call per symbol max, only if any kept-headline survives prefilter.)

### New DB table — rejected headlines (for audit / "Rejected Headlines" dashboard panel)

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

Retention: 30 days. Cleanup job runs daily (add to scheduler — see §10).

### Dashboard "News Feed" tab gets a new sub-section: "Rejected Headlines (last 7d)"

Streamlit panel showing recent rejections with columns: time | symbol | headline | source | filter_status. Search box to find a specific stock. "Promote keyword" button next to each headline that opens a copy-paste hint:

```
Add this keyword to material_keywords.yaml under tier_A:
  - <suggested keyword>
Then restart plutus-main.service.
```

(The button is just a UX nudge — no auto-edit. Editing YAML is manual.)

---

## 6. `/analyze` API — auth, rate limit, cache (Q10)

### Rate limit

Per-API-key: **30 calls/hour, sliding window**. Use `slowapi` (Redis-free, in-memory). On 429, return `{"error": "rate_limit_exceeded", "retry_after_seconds": <n>}`.

### Symbol-level cache

5-minute TTL keyed on `(symbol, exchange)`. Same cache used by:
- `/analyze` HTTP endpoint
- Telegram `/stock SYMBOL` command
- Dashboard "Run on-demand analysis" button

In-memory `dict[(symbol, exchange) -> (timestamp, response_dict)]`. Cleared on process restart (fine for MVP). Add `cache_hit: bool` field to API response.

```python
# pseudocode
def run_analysis_cached(symbol, exchange):
    key = (symbol.upper(), exchange.upper())
    now = time.time()
    if key in CACHE and (now - CACHE[key][0]) < 300:
        result = dict(CACHE[key][1])
        result["cache_hit"] = True
        return result
    result = run_analysis(symbol, exchange)
    result["cache_hit"] = False
    CACHE[key] = (now, dict(result))
    return result
```

### Add to OpenAPI schema

`X-API-Key` (existing) + 2 new response fields: `cache_hit: bool`, `rate_limit_remaining: int` (header `X-RateLimit-Remaining`).

---

## 7. LLM model — DeepSeek V4 Flash (Q11)

The new model the user has added is **DeepSeek V4 Flash**. Update model identifiers in config:

```python
# config.py
DEEPSEEK_FAST_MODEL: str = "deepseek/deepseek-v4-flash"        # all agents (replaces V3 chat)
DEEPSEEK_REASON_MODEL: str = "deepseek/deepseek-v4-flash"      # synthesizer (replaces R1)
```

**Both fast and reason models point to V4 Flash for now.** Single model across the pipeline. Synthesizer prompt is unchanged in content but the model env var lets us swap to a heavier reasoner later (`deepseek/deepseek-r1` or whatever's current) by changing one env var.

Cost estimate update: V4 Flash is cheaper than R1; per-stock cost drops from $0.02–0.05 to ~$0.01–0.02. Monthly: ~$2–4. Keep the spec's "$5–10/month" as a safe upper bound (covers headroom for news monitor + ad-hoc usage).

Update wherever model name appears: `08_agents.md`, `03_config_env.md`, `09_api.md` cost section, the PRD §9 table.

---

## 8. Outcome tracker fix (Q12)

### Bugs in current spec

1. Outcome `_pct` is computed against `entry_high` (zone upper bound), not actual fill. Real paper trade has a fill price; recommendations use the entry-zone midpoint as the assumed fill price.
2. `df.index >= rec.created_at` mixes UTC timestamp with NSE trading-day index. Trading-day boundaries are IST, not UTC.
3. When the same daily candle has both `High >= target1` AND `Low <= stop_loss`, the spec assumes target hit first. With swing trades, intraday order is unknowable from daily bars; the conservative rule is **stop hits first** (the worse outcome).
4. `hold_days_min` / `hold_days_max` are referenced but the schema has `hold_days` as a single field. Need to split.

### Fixes

**Schema** (additive ALTERs, backwards-compatible):

```sql
-- recommendations
ALTER TABLE recommendations ADD COLUMN entry_mid NUMERIC(12, 2);   -- (entry_low + entry_high)/2
ALTER TABLE recommendations ADD COLUMN hold_days_min INTEGER;
ALTER TABLE recommendations ADD COLUMN hold_days_max INTEGER;
-- hold_days stays as a backward-compat alias = hold_days_max
ALTER TABLE recommendations ADD COLUMN outcome_fill_price NUMERIC(12, 2);
ALTER TABLE recommendations ADD COLUMN outcome_exit_price NUMERIC(12, 2);
ALTER TABLE recommendations ADD COLUMN outcome_exit_date DATE;
```

**Synthesizer prompt** must now output `hold_days_min` and `hold_days_max` (e.g., "5-8" → min=5, max=8).
**`run_analysis`** must populate `entry_mid = (entry_low + entry_high) / 2` before insert.

**`track_recommendation_outcomes` algorithm:**

```python
import pytz
IST = pytz.timezone("Asia/Kolkata")

def track_recommendation_outcomes():
    today_ist = datetime.now(IST).date()
    with SessionLocal() as db:
        pending = db.query(Recommendation).filter(
            Recommendation.outcome.in_([None, OutcomeVerdict.PENDING])
        ).all()

        for rec in pending:
            created_ist = rec.created_at.astimezone(IST).date()
            trading_days_elapsed = nse_trading_days_between(created_ist, today_ist)

            if trading_days_elapsed < (rec.hold_days_min or 5):
                continue  # too early to call

            df = fetch_ohlcv(rec.symbol, days=trading_days_elapsed + 5)
            df = df[df.index.date > created_ist]   # strictly AFTER recommendation day
            if df.empty:
                continue

            fill = float(rec.entry_mid or rec.entry_high)
            stop = float(rec.stop_loss)
            t1 = float(rec.target1)
            t2 = float(rec.target2) if rec.target2 else None

            outcome = None
            outcome_pct = None
            outcome_exit_date = None
            outcome_exit_price = None

            for idx, row in df.iterrows():
                hit_t2 = t2 and row.High >= t2
                hit_t1 = row.High >= t1
                hit_stop = row.Low <= stop

                # Conservative ambiguity rule: stop wins on same-day collision.
                if hit_stop and (hit_t1 or hit_t2):
                    outcome = OutcomeVerdict.STOPPED
                    outcome_exit_price = stop
                elif hit_t2:
                    outcome = OutcomeVerdict.HIT_T2
                    outcome_exit_price = t2
                elif hit_t1:
                    outcome = OutcomeVerdict.HIT_T1
                    outcome_exit_price = t1
                elif hit_stop:
                    outcome = OutcomeVerdict.STOPPED
                    outcome_exit_price = stop

                if outcome:
                    outcome_exit_date = idx.date()
                    break

            if not outcome:
                if trading_days_elapsed >= (rec.hold_days_max or 10):
                    outcome = OutcomeVerdict.EXPIRED
                    outcome_exit_price = float(df.iloc[-1].Close)
                    outcome_exit_date = df.index[-1].date()
                else:
                    continue   # still in window

            outcome_pct = (outcome_exit_price - fill) / fill * 100
            rec.outcome = outcome
            rec.outcome_pct = outcome_pct
            rec.outcome_fill_price = fill
            rec.outcome_exit_price = outcome_exit_price
            rec.outcome_exit_date = outcome_exit_date
            rec.outcome_tracked_at = datetime.utcnow()
        db.commit()
```

`nse_trading_days_between` helper: count weekdays minus NSE holidays (load from `data/nse_holidays.txt` — checked-in static list, refreshed yearly; if missing, fall back to "weekdays only" with a logged warning).

Add new file: `src/plutus/data/nse_holidays.txt` (one ISO date per line; seed with 2026 holidays).

---

## 9. Telegram bot — separate process (Q13)

### Three systemd services (was: two)

| Service | Process | What it runs |
|---|---|---|
| `plutus-main.service` | `python -m src.main` | FastAPI on 8000 + APScheduler |
| `plutus-bot.service` | `python -m src.bot` | python-telegram-bot polling |
| `plutus-dashboard.service` | `streamlit run src/dashboard.py --server.port 8501` | Streamlit |
| (`postgresql.service`) | system | unchanged |

### Inter-process communication

`plutus-bot` needs to:
1. Receive push commands from `plutus-main` (e.g., "send weekly summary," "send news alert"). Mechanism: `plutus-main` calls a small **internal HTTP endpoint** on `plutus-bot` (localhost-only, port 8001):
   - `POST /push/weekly-summary` body: `{run_id: int}` → bot loads from DB and sends.
   - `POST /push/news-alert` body: `{event_id: int}` → bot loads from DB and sends.
2. Read DB directly for command handlers (`/portfolio`, `/stock`, `/buy`, `/sell`).
3. Call back into `plutus-main`'s `/analyze` for `/stock SYMBOL` (uses the rate limit + cache).

`plutus-bot` runs its own FastAPI app on `127.0.0.1:8001` for receiving pushes. Bound to localhost only — no auth needed (loopback). Bot also uses python-telegram-bot's Application in polling mode in the same event loop.

Add new env vars:

```
BOT_INTERNAL_PORT: int = 8001
BOT_INTERNAL_BIND: str = "127.0.0.1"
```

### Folder layout impact

```
src/
├── main.py     # FastAPI(port 8000) + APScheduler. Imports from plutus.api, plutus.db, etc.
├── bot.py      # FastAPI(port 8001 localhost-only) + Telegram polling. Imports from plutus.alerts.telegram_bot.
└── dashboard.py
```

`alerts/telegram_bot.py` no longer wires into `main.py`'s app. It exposes:
- `build_telegram_app() -> Application`
- `register_internal_routes(app: FastAPI)` — registers the `/push/*` endpoints.
- Command handlers (`cmd_stock`, `cmd_portfolio`, etc.) and push functions (`push_weekly_summary`, `push_news_alert`).

### `main.py` changes

When `main.py` needs to push to the bot, it does:

```python
import httpx
async def trigger_weekly_push(run_id: int):
    async with httpx.AsyncClient() as cli:
        await cli.post(f"http://{BOT_INTERNAL_BIND}:{BOT_INTERNAL_PORT}/push/weekly-summary",
                       json={"run_id": run_id}, timeout=10)
```

If bot service is down, log a warning and continue (don't fail the weekly run).

---

## 10. Scheduler additions

The scheduler now manages five jobs (was: three):

| Job ID | Cron | Function | Owner process |
|---|---|---|---|
| `weekly_pipeline` | `Sun 18:00 IST` | full research run | `plutus-main` |
| `weekly_revalidate` | `Mon 09:10 IST` | NEW — gap re-validation | `plutus-main` |
| `news_monitor` | `Mon-Fri */60 min, 09:00-15:59 IST` | hourly news scan | `plutus-main` |
| `outcome_tracker` | `Mon-Fri 16:30 IST` | recommendation outcome update | `plutus-main` |
| `rejected_headlines_cleanup` | `Daily 03:00 IST` | NEW — delete rejected_headlines older than 30d | `plutus-main` |

Telegram bot has no scheduler.

---

## 11. Dashboard — 8 tabs (Q15) + new history tab + rejected headlines

8 tabs as in PRD Flow 8: Home, Signals, Portfolio, Strategy Lab, News Feed, Watchlist, History, Settings.

**News Feed** sub-sections:
1. "Material Events (last 7d)" — alerts that fired
2. "Rejected Headlines (last 7d)" — NEW per §5

**History** tab — full per-week drilldown. Loads `weekly_runs` rows in a date-sortable table. Click a row → shows:
- Markdown body of `reports/weekly/<date>.md` (if file present on disk)
- Recommendations table for that run
- Outcome summary: count of HIT_T1, HIT_T2, STOPPED, EXPIRED, PENDING
- Equity curve overlay vs Nifty50 for the week

**Settings** is a tab, not a sidebar. Confirmed.

---

## 12. Service & cost summary

Update PRD §6 process map and §15 deployment to reflect:

- 4 systemd services (postgres + plutus-main + plutus-bot + plutus-dashboard)
- Cost: ~$2–10/month OpenRouter (V4 Flash)
- All other services free
- Bot adds ~30 MB RAM idle → total idle ~500 MB / 12 GB

---

## 13. Decision log (Q1–Q15) — for traceability

| # | Question | Decision |
|---|---|---|
| Q1 | Project name | Plutus everywhere; rename indiatradeai → plutus |
| Q2 | Code path | `personal-projects/plutus-app/src/` |
| Q3 | Strategy bundles | 5 peer bundles (Composite is a peer) |
| Q4 | Universe screener | Nifty 500 + MidCap 150 seed CSV; OHLCV-derived liquidity filters; no `Ticker.info` |
| Q5 | `/buy` semantics | Literal-shares + risk warning + /confirm flow |
| Q6 | Max open positions | 4 advisory; 10 hard cap |
| Q7 | Weekly run cadence | Sunday research + Monday 09:10 re-validation |
| Q8 | News classification | Single batched LLM call per symbol |
| Q9 | Material prefilter | Hard tiered prefilter (A+B enabled by default; C in code, disabled); stoplist |
| Q10 | API protection | 30/hr per key + 5-min symbol cache |
| Q11 | LLM model | DeepSeek V4 Flash for both fast + synthesizer |
| Q12 | Outcome tracker | Patched (entry-mid fill, IST trading days, stop-first ambiguity, hold_days_min/max split) |
| Q13 | Telegram process | Split — separate `plutus-bot.service` |
| Q14 | Reports git | `.gitignore`d; no auto-commit |
| Q15 | Dashboard tabs | 8 tabs (Settings is a tab) |

---

## 14. Worker instructions (read before editing any spec)

1. **Open and read your assigned file first.** Match its style, headings, and code-block conventions.
2. **Delete or replace any content that contradicts this CHANGE_SPEC.** When in doubt, this doc wins.
3. **Do not change file paths inside the spec to anything not listed in §0.**
4. **Keep all existing decisions that are not contradicted here** (e.g., the LangGraph topology, RSS feed list, Backtrader as the engine, PostgreSQL 16, the systemd patterns).
5. **Cross-references stay accurate.** When you reference another spec file (e.g., "see `04_database.md`"), make sure the section you point to actually exists in the new version.
6. **Code blocks must be runnable Python** that matches the new module structure (`from plutus.data.universe import ...`).
7. **No new TODOs or placeholders.** Every contract listed here must be specified concretely.
8. **The PRD also gets rewritten.** Both the original (`first-i-want-u-velvety-tide.md`) and the new PRD live in `specs/`. Output the new one as `PRD.md` in `specs/`. Leave the old PRD untouched (it is preserved as the historical pre-revision artifact).
