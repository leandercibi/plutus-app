# PRD: Plutus — Indian Equities Recommendation Engine

---

## 1. Context & Problem Statement

A retail trader with ₹1,00,000 INR capital wants to trade Indian equities (NSE/BSE) on a short-term basis (weekly horizon). The core problem: making informed buy/sell/hold decisions requires synthesising technical analysis, news sentiment, institutional (MF/FII) signals, and risk management simultaneously — a task that is cognitively overwhelming for a solo trader.

Plutus replaces manual research with an agentic pipeline powered by DeepSeek V4 Flash (via OpenRouter), running 5 peer trading-strategy bundles, and exposing results through Telegram, a Streamlit dashboard, and an HTTP API (for Hermes agent integration).

**Intended outcome:** Every Sunday evening the user receives a prioritised, actionable recommendation list for the coming week, re-validated against Monday's open. Intraday, breaking news on tracked stocks triggers instant alerts. On-demand stock queries can be answered in ~20 seconds from any surface (Telegram, Hermes, Dashboard).

---

## 2. User Persona

**Primary user:** Solo retail trader
- Capital: ₹1,00,000 INR
- Experience: Intermediate (understands basic TA, familiar with NSE)
- Available time: Reviews recommendations Sunday evening; checks alerts on mobile
- Comfort with tech: Can run a terminal command, owns an OCI instance
- Risk tolerance: Max 5% capital at risk per trade

**Secondary caller:** A Hermes agent (Nous Hermes model) that calls the `/analyze` endpoint as a tool to answer user stock queries programmatically.

---

## 3. User Interaction Surfaces

| Surface | Use Case | Always-on? |
|---|---|---|
| Telegram Bot | Alerts, on-demand queries, portfolio commands | Yes (polling) |
| Streamlit Dashboard | Visual review of recommendations, backtest results, portfolio | Yes (port 8501) |
| HTTP API (`/analyze`) | Hermes agent tool calls, programmatic access | Yes (port 8000) |
| WhatsApp (CallMeBot) | Critical news alerts only (secondary channel) | Yes (push only) |

---

## 4. User Flows

### Flow 1: Weekly Recommendation Review (Primary Flow)
```
Sunday 18:00 IST — Automated trigger (APScheduler, runs against Friday close)
  │
  ├── Universe screener (curated seed CSV: Nifty 500 + MidCap 150)
  │   Filter: last_close ₹50–₹5000, avg_daily_volume_30d > 5L,
  │           avg_traded_value_30d > ₹10 Cr, not in F&O ban
  │   Output: ~150–200 candidate stocks
  │
  ├── Run 5 peer strategy bundles (Backtrader, last 90 days)
  │   → Rank each candidate by backtested win rate this week
  │   → Strategy Selector picks top 2 of 5 bundles for current market regime
  │
  ├── Top 20 candidates enter LangGraph agent pipeline
  │   → Technical Agent (DeepSeek V4 Flash) — indicator confluence
  │   → Sentiment Agent (DeepSeek V4 Flash) — news + Reddit scoring
  │   → Smart Money Agent (DeepSeek V4 Flash) — MF/FII signal
  │   → Risk Manager (DeepSeek V4 Flash) — position size, R:R check
  │   → Synthesizer (DeepSeek V4 Flash) — final verdict per stock
  │
  ├── Results saved to PostgreSQL; weekly_runs row + reports/weekly/<date>.md
  │
  ├── Telegram message sent to user:
  │   "📊 Weekly Picks — 30 May 2026
  │    ✅ BUY (4 stocks): RELIANCE, TATAMOTORS, HDFCBANK, INFY
  │    ⏳ WATCH (3 stocks): WIPRO, SUNPHARMA, ONGC
  │    ❌ AVOID this week: Nifty trend weak — reduce new entries
  │    Reply /signals for details or /stock RELIANCE for deep dive"
  │
  └── Dashboard auto-refreshes with new recommendations

Monday 09:10 IST — Re-validation pass (no LLM calls; pure price math)
  │
  ├── For each BUY/WATCH from latest weekly_run, fetch live LTP
  │   → If LTP > entry_high * 1.02 → BUY downgraded to WATCH (gapped past entry)
  │   → If LTP < stop_loss → BUY downgraded to AVOID (already broken)
  │   → Else → unchanged
  │
  ├── Update recommendations.recommendation, revalidation_note, revalidated_at
  │
  └── Single Telegram delta:
      "📊 Monday open: 1 BUY downgraded (RELIANCE → WATCH, gapped +2.4%)"
```

### Flow 2: On-Demand Stock Analysis (Telegram)
```
User sends to Telegram Bot: "TATAMOTORS" or "/stock TATAMOTORS"
  │
  ├── Bot acknowledges: "Analysing TATAMOTORS... ⏳ (~20 sec)"
  │
  ├── Bot calls plutus-main /analyze (cached: 5-min TTL per (symbol, exchange))
  │   → Fetch 90-day OHLCV
  │   → Run all 5 peer strategy bundles
  │   → Run full agent pipeline (Technical + Sentiment + SmartMoney + Risk + Synthesizer)
  │
  └── Bot replies with structured report:
      "📈 TATAMOTORS — NSE | ₹789.50
       Recommendation: ✅ BUY (Confidence: 7.8/10)
       Entry Zone: ₹782–₹795 (mid ₹788.50)
       Target 1: ₹845 | Target 2: ₹890
       Stop Loss: ₹755 (4.4% risk)
       Position: 126 shares (₹99,477 — 99.5% capital)
       Hold: 6–9 trading days
       Strategy: Breakout + Trend confluence
       Smart Money: 4 MFs accumulating ↑, FII net buyer
       Sentiment: Positive (+3/5) — EV push coverage
       ⚠️ No open positions before entering this trade"
```

### Flow 3: Hermes Agent Tool Call
```
User asks their Hermes agent: "Should I buy Infosys right now?"
  │
  ├── Hermes identifies tool: analyze_stock
  ├── Hermes calls: POST http://<OCI_IP>:8000/analyze
  │   Body: {"symbol": "INFY", "exchange": "NSE"}
  │   Headers: X-API-Key: <key>
  │
  ├── plutus-main authenticates, applies 30/hr rate limit + 5-min cache
  ├── Returns structured JSON (see Section 8) with cache_hit + rate_limit_remaining
  │
  └── Hermes reads JSON → answers user in natural language:
      "Based on current analysis, Infosys shows a moderate BUY signal
       with 6.9/10 confidence. Entry around ₹1,820–₹1,835, target
       ₹1,920, stop at ₹1,775. Three mutual funds are accumulating.
       Risk: 3.1% of your capital."
```

### Flow 4: News Alert (Intraday, Real-Time)
```
Hourly background job (APScheduler, Mon–Fri */60 min, 09:00–15:59 IST)
  │
  ├── Fetches latest news for: watchlist stocks + open positions
  │   Sources: NewsAPI, Google News RSS, Economic Times RSS, MoneyControl RSS
  │
  ├── Hard prefilter (data/material_keywords.yaml, tiers A+B by default)
  │   → Stoplist match → reject (saved to rejected_headlines, status='stoplist')
  │   → No tier keyword → reject (saved to rejected_headlines, status='no_keyword')
  │   → Tier hit → kept for LLM batch classification
  │
  ├── If any kept headlines for a symbol:
  │   → Single batched DeepSeek V4 Flash call per symbol
  │   → Classifies: material event? (earnings, regulatory, promoter, rating, block deal)
  │   → Sentiment: strongly positive / strongly negative / neutral
  │
  ├── If material event detected:
  │   → Telegram INSTANT alert via plutus-bot push endpoint:
  │     "🚨 NEWS ALERT — SUNPHARMA
  │      USFDA issues import alert on Halol plant
  │      Signal: ⬇️ SELL / EXIT if holding
  │      Current price: ₹1,234 | Expected impact: -3% to -7%
  │      /stock SUNPHARMA for full re-analysis"
  │   → WhatsApp backup alert (if enabled)
  │
  └── Non-material news → news_events row, dashboard feed only
      Rejected headlines → rejected_headlines table (30-day retention)
```

### Flow 5: Mock Portfolio Management (Multi-Portfolio with /confirm)
```
User sends: /portfolio list
  → Bot: "📁 Your Mock Portfolios:
          1. aggressive_momentum  | Capital: ₹1,00,000 | P&L: +₹4,210 (+4.21%)
          2. conservative_swing   | Capital: ₹1,00,000 | P&L: +₹1,890 (+1.89%)
          3. smc_test             | Capital: ₹1,00,000 | P&L: -₹820 (-0.82%)
          /portfolio <name> for details"

User sends: /portfolio new aggressive_momentum 100000
  → Bot: "✅ Created mock portfolio 'aggressive_momentum' with ₹1,00,000 capital."

User sends: /portfolio aggressive_momentum
  → Bot: "💼 aggressive_momentum — ₹1,00,000 initial
          Open Positions (2):
          • RELIANCE: 42 shares | Bought @ ₹2,389 on 26-May | Current: ₹2,431 | P&L: +₹1,764 (+1.75%)
          • HDFCBANK: 68 shares | Bought @ ₹1,672 on 27-May | Current: ₹1,659 | P&L: -₹884 (-0.77%)

          Closed Trades: 7 | Win: 5 | Loss: 2 | Win Rate: 71%
          Realised P&L: +₹6,340
          Unrealised P&L:   +₹880
          Current Value:    ₹1,07,220
          Cash Available:   ₹80,340

          /portfolio aggressive_momentum history — full trade log"

User sends: /buy aggressive_momentum TATAMOTORS 790 50
  → Bot pre-trade check (advisory; pending trade held in memory, 60s TTL):
      "⚠️ Pre-trade check:
         Shares: 50 × ₹790 = ₹39,500 (39.5% of capital)
         Risk: ₹1,750 (1.75% — within 5% limit ✓)
         Open positions after: 5 (above advisory limit of 4 ⚠)

       Confirm? Reply /confirm or /cancel within 60 seconds."

User sends: /confirm
  → "✅ Logged: BUY 50 × TATAMOTORS @ ₹790 in 'aggressive_momentum'
      Capital used: ₹39,500 | Cash remaining: ₹40,840"

User sends: /sell aggressive_momentum TATAMOTORS 845 50
  → Same /confirm flow, then:
      "✅ Logged: SELL 50 × TATAMOTORS @ ₹845 in 'aggressive_momentum'
       Profit: +₹2,750 (+6.96%) on this trade
       Portfolio realised P&L now: +₹9,090"

Hard reject (no /confirm prompt): capital used > available cash.

Dashboard → Portfolio tab:
  - Dropdown to switch between all named portfolios
  - Equity curve per portfolio (overlaid comparison chart)
  - Trade log table: date, symbol, buy price, sell price, qty, P&L, holding days
  - Portfolio comparison card: side-by-side stats for all portfolios
  - Best/worst trade highlights per portfolio
```

### Flow 6: Watchlist Management
```
User sends: /watch add BAJAJFINSV
  → Bot: "✅ BAJAJFINSV added to watchlist. You'll get news alerts
          and it will be included in next weekly analysis."

User sends: /watch list
  → Bot: Shows all watchlist stocks with current sentiment score

User sends: /watch remove WIPRO
  → Bot: "✅ WIPRO removed from watchlist."

User sends: /watch BAJAJFINSV
  → Same as /stock — triggers on-demand analysis
```

### Flow 6b: Weekly Suggestion History Review
```
Dashboard → "History" tab OR
User sends: /history 2026-05-25
  │
  └── Shows that week's full recommendation report:
      "📋 Weekly Analysis — 25 May 2026
       Market Regime: Bullish trending (Nifty above EMA50)
       Strategies Selected: Bundle 3 (Breakout) + Bundle 1 (Trend) — top 2 of 5

       BUY Signals (4 stocks):
       ┌─────────────────────────────────────────────────────┐
       │ RELIANCE | Score: 8.2 | Entry: 2375-2395 | T: 2480 │
       │ Reasoning: "Strong breakout from 6-week range...    │
       │ 3 MFs accumulating, FII net buyer ₹340Cr"          │
       ├─────────────────────────────────────────────────────┤
       │ TATAMOTORS | Score: 7.8 | Entry: 782-795 | T: 845  │
       │ Reasoning: "EV segment coverage positive, RSI 64..." │
       └─────────────────────────────────────────────────────┘

       Outcome tracking (auto-updated after hold_days_max elapsed):
       • RELIANCE: Hit Target 1 ✅ (+3.6%) — exited 2026-06-02 @ ₹2,480
       • TATAMOTORS: Stopped out ❌ (-4.8%) — exited 2026-05-29 @ ₹755"

Storage: each weekly run saves a Markdown file:
  src/reports/weekly/2026-05-25.md   ← human-readable; gitignored
  + DB row in weekly_runs table       ← querying / charting
```

### Flow 7: Backtest & Strategy Comparison (Dashboard)
```
User opens Dashboard → navigates to "Strategy Lab" tab
  │
  ├── View: Table of all 5 peer strategy bundles
  │   Columns: Win Rate, Avg Return/Trade, Max Drawdown,
  │            Sharpe Ratio, Total Trades (90 days), Current Weight
  │
  ├── Chart: Equity curve for each bundle (overlaid)
  │
  ├── Trigger manual backtest:
  │   Select: Stock | Date range | Strategy bundle
  │   → Run → Show trade log + P&L chart
  │
  └── Paper trading feed: every simulated trade logged with
      entry/exit/reason/outcome
```

### Flow 8: Dashboard Overview (Full View)
```
Dashboard tabs (8):
  1. 🏠 Home         — Weekly summary card, top picks at a glance
  2. 📊 Signals      — Full recommendation table, sortable by score
  3. 💼 Portfolio    — Paper positions, P&L chart, trade history
  4. 🧪 Strategy Lab — Backtest runner, strategy comparison
  5. 📰 News Feed    — Material Events (7d) + Rejected Headlines (7d) sub-sections
  6. 👁 Watchlist    — Manage tracked stocks, per-stock mini-analysis
  7. 📋 History      — Past weekly reports, outcomes, searchable recommendation log
  8. ⚙️ Settings     — Risk %, capital, watchlist import, API key display (tab, not sidebar)
```

---

## 5. Feature Requirements

### P0 — Must Have (Week 1–2)
| # | Feature | Description |
|---|---|---|
| F1 | NSE Universe Screener | Curated seed CSV (Nifty 500 + MidCap 150) → OHLCV-based liquidity filter → ~150–200 tradeable |
| F2 | 5 Peer Strategy Bundles | Backtrader implementation; Composite is a peer (not a meta-filter) |
| F3 | Weekly Pipeline | Sunday 18:00 IST automated run with full agent pipeline |
| F3a | Monday Re-validation | NEW — Mon 09:10 IST gap check; downgrades BUY/WATCH on adverse open; no LLM calls |
| F4 | LangGraph Agents | Technical, Sentiment, Smart Money, Risk, Synthesizer |
| F5 | DeepSeek V4 Flash via OpenRouter | All LLM calls (fast + synthesizer) |
| F6 | On-Demand Analysis | `/stock SYMBOL` triggers cached deep analysis |
| F7 | Telegram Bot | Separate process; commands (/signals /portfolio /stock /watch /buy /sell /confirm /history) |
| F8 | Multi-Portfolio Mock Trading | Named portfolios, /buy + /sell + /confirm flow, advisory + hard limits, per-portfolio P&L |
| F9 | News Monitor | Hourly job; tiered keyword prefilter (A+B); single batched LLM call per symbol |
| F9a | Rejected-Headlines Audit | NEW — `rejected_headlines` table; dashboard panel; 30-day retention |
| F10 | HTTP API `/analyze` | 30/hr per-key rate limit; 5-min symbol cache; `cache_hit` + `rate_limit_remaining` in response |
| F11 | Streamlit Dashboard | All 8 tabs as described in Flow 8 |
| F11a | Weekly History Store | Each weekly run as `src/reports/weekly/YYYY-MM-DD.md` (gitignored) + DB row |
| F11b | Outcome Tracking | Auto-update outcomes (entry-mid fill, IST trading days, stop-first ambiguity) |

### P1 — Should Have (Week 2 / shortly after)
| # | Feature |
|---|---|
| F13 | Reddit Sentiment (PRAW) — r/IndianStreetBets, r/IndiaInvestments |
| F14 | MF Portfolio Tracking (AMFI + mftool) |
| F15 | FII/DII Daily Flow Signal |
| F16 | WhatsApp Alerts (CallMeBot) |
| F17 | Cloudflare Tunnel (public dashboard URL) |

### P2 — Nice to Have (Post-MVP)
| # | Feature |
|---|---|
| F19 | Telegram inline keyboard (tap to add to watchlist, confirm paper trade) |
| F20 | Weekly performance email report (PDF via Streamlit export) |
| F21 | Strategy auto-weight tuning (weight bundles by last 4-week performance) |

---

## 6. System Architecture

### Process Map
```
OCI A1.flex — 2 CPU / 12 GB RAM — Ubuntu 22.04 (ARM64)

Service: postgresql.service  (system unit)
  └── PostgreSQL 16 — DB `plutus_db`, user `plutus`

Service: plutus-main.service  (python -m src.main)
  ├── FastAPI app (uvicorn, port 8000)
  │   ├── POST /analyze    — on-demand stock analysis (auth + 30/hr rate limit + 5-min cache)
  │   ├── GET  /weekly     — latest weekly recommendations
  │   └── GET  /health     — liveness check
  └── APScheduler
      ├── Sun 18:00 IST                  — weekly_pipeline()
      ├── Mon 09:10 IST                  — weekly_revalidate()    [NEW]
      ├── Mon–Fri */60 min, 09:00–15:59  — news_monitor()
      ├── Mon–Fri 16:30 IST              — outcome_tracker()
      └── Daily 03:00 IST                — rejected_headlines_cleanup()  [NEW]

Service: plutus-bot.service  (python -m src.bot)
  ├── python-telegram-bot (polling mode)
  │   └── Command handlers: /stock /signals /portfolio /buy /sell /confirm
  │                         /cancel /watch /history
  └── FastAPI app (uvicorn, 127.0.0.1:8001 — loopback only, no auth)
      ├── POST /push/weekly-summary  — body {run_id}
      └── POST /push/news-alert      — body {event_id}

Service: plutus-dashboard.service  (streamlit run src/dashboard.py --server.port 8501)
  └── Streamlit (8 tabs)

Optional: Cloudflare Tunnel → exposes port 8501 publicly
```

### Folder Structure (new module path)
```
/Users/leander/personal-projects/plutus-app/        # local dev
/home/ubuntu/plutus-app/                            # OCI deploy
└── src/
    ├── plutus/                       # canonical package — `from plutus.X.Y import Z`
    │   ├── __init__.py
    │   ├── config.py                 # all settings from env vars
    │   ├── data/
    │   │   ├── universe.py           # seed CSV + OHLCV-based filters; no Ticker.info
    │   │   ├── ohlcv.py              # historical + live OHLCV (yfinance, ~15-min delayed)
    │   │   ├── news.py               # NewsAPI + RSS + prefilter + batched DeepSeek classifier
    │   │   ├── reddit.py             # PRAW sentiment scraper
    │   │   ├── smart_money.py        # AMFI mftool + NSE FII/DII data
    │   │   ├── seed_universe.csv     # checked-in: Nifty 500 + MidCap 150
    │   │   ├── material_keywords.yaml# tiered prefilter (A, B, C + stoplist)
    │   │   ├── nse_holidays.txt      # IST trading-day calendar
    │   │   └── fno_ban_list.txt      # daily-refreshed best-effort
    │   ├── strategies/
    │   │   ├── base.py
    │   │   ├── bundle_trend.py
    │   │   ├── bundle_reversal.py
    │   │   ├── bundle_breakout.py
    │   │   ├── bundle_smc.py
    │   │   └── bundle_composite.py   # PEER bundle (3-of-4 internal agreement)
    │   ├── backtesting/
    │   │   ├── runner.py             # run_all_bundles() → Dict[str, BundleResult] (5 keys)
    │   │   └── paper_trader.py
    │   ├── agents/
    │   │   ├── graph.py              # LangGraph StateGraph
    │   │   ├── technical.py
    │   │   ├── sentiment.py
    │   │   ├── smart_money.py
    │   │   ├── risk_manager.py
    │   │   ├── synthesizer.py        # outputs hold_days_min, hold_days_max, entry_mid
    │   │   └── prompts.py
    │   ├── alerts/
    │   │   ├── telegram_bot.py       # build_telegram_app(), register_internal_routes(),
    │   │   │                         # cmd_* handlers, push_weekly_summary, push_news_alert
    │   │   └── whatsapp.py
    │   ├── api/
    │   │   └── routes.py             # /analyze with rate limit + cache
    │   └── db/
    │       ├── models.py             # SQLAlchemy ORM
    │       ├── session.py
    │       └── schema.sql
    ├── main.py                       # entry: plutus-main (FastAPI 8000 + scheduler)
    ├── bot.py                        # entry: plutus-bot (Telegram polling + FastAPI 8001)
    ├── dashboard.py                  # entry: plutus-dashboard (Streamlit)
    ├── reports/
    │   └── weekly/                   # YYYY-MM-DD.md per run; .gitignored
    ├── requirements.txt
    └── .env                          # gitignored
```

---

## 7. Database Schema

```sql
-- Weekly analysis runs (one row per weekly run)
weekly_runs (
  id, run_date, market_regime, nifty_trend,
  strategy_selected, stocks_screened, stocks_analysed,
  total_buy_signals, total_watch_signals,
  report_md_path,                                   -- src/reports/weekly/YYYY-MM-DD.md
  created_at
)

-- Per-stock recommendations (many rows per weekly_run)
recommendations (
  id, weekly_run_id, symbol, exchange, recommendation,
  confidence, entry_low, entry_high,
  entry_mid,                                        -- NEW: (entry_low + entry_high)/2; outcome fill basis
  target1, target2, stop_loss, rr_ratio,
  hold_days,                                        -- backward-compat alias = hold_days_max
  hold_days_min,                                    -- NEW
  hold_days_max,                                    -- NEW
  strategy_used,
  technical_score, sentiment_score, smart_money_score,
  reasoning_text,
  outcome,                                          -- NULL/PENDING/HIT_T1/HIT_T2/STOPPED/EXPIRED
  outcome_pct,
  outcome_fill_price,                               -- NEW: actual fill basis (entry_mid)
  outcome_exit_price,                               -- NEW: T1, T2, stop, or last close on expiry
  outcome_exit_date,                                -- NEW: date the outcome resolved
  outcome_tracked_at,
  revalidation_note,                                -- NEW: Monday gap-check note
  revalidated_at,                                   -- NEW: timestamp of Monday revalidation
  created_at
)

-- Named mock portfolios
mock_portfolios (
  id, name, initial_capital, created_at, notes
)

-- Paper trades (linked to a mock portfolio)
paper_trades (
  id, portfolio_id,                                 -- FK → mock_portfolios
  symbol, direction,                                -- LONG/SHORT
  entry_price, entry_date, shares, capital_used,
  exit_price, exit_date, realised_pnl, realised_pnl_pct,
  strategy_used, status,                            -- OPEN/CLOSED
  exit_reason,                                      -- TARGET/STOP/MANUAL/SIGNAL
  linked_recommendation_id                          -- FK → recommendations (optional)
)

-- Watchlist
watchlist (
  id, symbol, exchange, added_at, notes
)

-- News events (kept after prefilter + LLM classification)
news_events (
  id, symbol, headline, source, published_at,
  sentiment,                                        -- positive/negative/neutral
  is_material, alert_sent, created_at
)

-- NEW: Rejected headlines (audit trail; 30-day retention)
rejected_headlines (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20),
  headline TEXT NOT NULL,
  source VARCHAR(50),
  published_at TIMESTAMP,
  filter_status VARCHAR(20),                        -- 'stoplist' | 'no_keyword'
  rejected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_rejected_symbol_at ON rejected_headlines (symbol, rejected_at DESC);

-- Strategy backtest results (refreshed weekly; 5 rows — one per peer bundle)
backtest_results (
  id, bundle_name, run_date, win_rate, avg_return,
  max_drawdown, sharpe_ratio, total_trades, weight_assigned
)
```

---

## 8. API Contract (Hermes Integration)

### POST /analyze
```
Request:
  Headers: X-API-Key: <key>
  Body: { "symbol": "RELIANCE", "exchange": "NSE" }  // exchange optional

Response (200):
  {
    "symbol": "RELIANCE",
    "exchange": "NSE",
    "current_price": 2389.50,
    "recommendation": "BUY",           // BUY | SELL | HOLD | WATCH | AVOID
    "confidence": 7.5,                 // 0–10
    "entry_zone": [2375, 2395],
    "entry_mid": 2385.00,
    "targets": [2460, 2520],
    "stop_loss": 2330,
    "risk_reward": 1.87,
    "position": {
      "shares": 102,
      "capital": 24368,
      "pct_of_portfolio": 24.4,
      "max_loss_inr": 4998
    },
    "hold_days": "5-8",
    "hold_days_min": 5,
    "hold_days_max": 8,
    "strategy": "Bundle 3 + Bundle 1 (top 2 of 5)",
    "signals": {
      "technical":   { "score": 7.5, "patterns": ["EMA crossover", "Volume breakout"] },
      "sentiment":   { "score": 3.0, "summary": "Positive Jio coverage" },
      "smart_money": { "mf_accumulating": 3, "fii": "net_buyer" }
    },
    "risk_flags": [],
    "reasoning": "...",
    "analysis_time_sec": 18.4,
    "cache_hit": false,                // NEW
    "rate_limit_remaining": 27         // NEW (also exposed via X-RateLimit-Remaining header)
  }

Response (422): symbol not found / not on NSE
Response (429): { "error": "rate_limit_exceeded", "retry_after_seconds": <n> }
Response (503): upstream data fetch failed
```

**Rate limit:** 30 calls/hour per API key, sliding window (slowapi, in-memory).
**Cache:** 5-minute TTL per `(symbol, exchange)`. Shared across `/analyze`, Telegram `/stock`, dashboard "Run on-demand" button.

---

## 9. Agent Design (LangGraph)

### Graph Flow
```
START
  │
  ├──(parallel)──► Technical Agent   ──┐
  ├──(parallel)──► Sentiment Agent   ──┤
  ├──(parallel)──► Smart Money Agent ──┤
  │                                    ▼
  │                             Risk Manager Agent
  │                                    │
  └──────────────────────────────► Synthesizer Agent
                                        │
                                      END
```

### Agent → Model Mapping
| Agent | Model | Why |
|---|---|---|
| Technical | `deepseek/deepseek-v4-flash` | Fast, pattern interpretation |
| Sentiment | `deepseek/deepseek-v4-flash` | Fast, text classification |
| Smart Money | `deepseek/deepseek-v4-flash` | Fast, data interpretation |
| Risk Manager | `deepseek/deepseek-v4-flash` | Deterministic math, light reasoning |
| Synthesizer | `deepseek/deepseek-v4-flash` | Multi-source synthesis (env-swappable to a heavier reasoner later) |

Both `DEEPSEEK_FAST_MODEL` and `DEEPSEEK_REASON_MODEL` point to `deepseek/deepseek-v4-flash` for now. Single model across the pipeline; swap one env var to upgrade the synthesizer.

### Cost Estimate (V4 Flash)
```
Per stock analysis (on-demand):    ~5 LLM calls → ~$0.01–0.02
Weekly run (20 stocks full pass):  ~100 LLM calls → ~$0.20–0.50
Monthly typical:                   ~$2–4
Monthly upper bound (heavy ad-hoc + news monitor): ~$5–10
```

---

## 10. Strategy Bundle Summary

**5 peer bundles. All run independently. Composite is a peer, not a meta-filter.**
The runner returns `Dict[bundle_name, BundleResult]` with 5 keys.

| Bundle | Core Logic | Key Indicators | Best Market Condition |
|---|---|---|---|
| 1: Trend | EMA crossover + momentum + volume | EMA 9/21/50, RSI > 55, Volume | Trending (bull/bear) |
| 2: Reversal | Oversold/overbought + divergence | Bollinger, RSI < 30/>70, MACD div | Ranging / exhausted trend |
| 3: Breakout | Consolidation escape + volume confirm | ATR, Volume ratio, Opening Range | Pre-breakout compression |
| 4: SMC | FVG fill + Order Block reaction + Liq Grab | FVG detection, volume, structure | All, especially volatile |
| 5: Composite | Trades only when 3-of-4 of bundles 1–4 agree on the same bar | All above | Low-noise, high-confidence only |

**Weekly Strategy Selection:**
- Run all 5 peer bundles on last 90 days every Sunday.
- Rank by Sharpe ratio for current week's market regime.
- **Top 2 of 5 bundles** → primary signals; their agreement on a stock raises allocation weight.

---

## 11. Data Sources

| Source | Data | Cost | Update Freq |
|---|---|---|---|
| yfinance (.NS / .BO) | OHLCV historical + intraday | Free | 15-min delay |
| NewsAPI (free tier) | 100 req/day, headlines | Free | Hourly |
| Google News / ET / MC RSS | Unlimited headlines | Free | On-fetch |
| PRAW (Reddit API) | r/IndianStreetBets etc | Free, 60 req/min | Hourly |
| mftool (AMFI) | All MF portfolio holdings | Free, Python lib | Monthly |
| NSE website (FII/DII) | Institutional flow data | Free, scrape | Daily |
| NSE bulk deals | Large block trades | Free | End of day |

---

## 12. System Efficiency & Resource Usage

### Weekly Run Profile (Sunday 18:00 IST, ~25 min total)
```
Phase                                Time      CPU    RAM
─────────────────────────────────────────────────────────
Universe screen (seed CSV + OHLCV)   2 min     15%    800 MB
Backtest 5 bundles × 200 stocks      12 min    85%    3.5 GB
Top 20 agent pipeline                8 min     30%    1.2 GB
DB writes + notification             1 min     5%     200 MB
─────────────────────────────────────────────────────────
Total                                ~25 min          Peak 4 GB
```

### Monday Re-validation Profile (~30 sec, no LLM)
```
Phase                          Time
───────────────────────────────────
Fetch live LTP for ~10 recs    20 sec
Price-math + DB updates        5 sec
Telegram delta push            2 sec
───────────────────────────────────
Total                          ~30 sec
```

### On-Demand Analysis Profile (~20 sec, cached responses < 100 ms)
```
Phase                         Time
──────────────────────────────────
Fetch OHLCV (90 days)         2 sec
Run 5 peer bundles (1 stock)  3 sec
Fetch news (prefiltered)      2 sec
LangGraph agent pipeline      10–15 sec
DB write                      <1 sec
Total                         ~20 sec (or <100 ms on cache hit)
```

### Always-On Resource Usage (idle)
```
plutus-main (FastAPI 8000 + scheduler):  ~120 MB RAM
plutus-bot (Telegram + FastAPI 8001):    ~30 MB RAM
plutus-dashboard (Streamlit):            ~150 MB RAM
PostgreSQL:                              ~200 MB RAM
Total idle:                              ~500 MB / 12 GB — very light
```

---

## 13. MVP Scope (2 Weeks)

### Week 1 Deliverables
- [ ] OCI environment setup (Python 3.11, PostgreSQL 16, venv) at `/home/ubuntu/plutus-app/`
- [ ] yfinance data pipeline + curated seed-CSV universe screener (`plutus.data.universe`)
- [ ] All 5 peer strategy bundles (Backtrader)
- [ ] LangGraph agent pipeline with DeepSeek V4 Flash via OpenRouter
- [ ] Paper trading engine + DB schema (incl. NEW columns + `rejected_headlines`)
- [ ] News fetcher + tiered keyword prefilter + batched DeepSeek classifier

### Week 2 Deliverables
- [ ] `plutus-main` (FastAPI on 8000 with rate limit + cache, APScheduler with 5 jobs)
- [ ] `plutus-bot` (separate process, Telegram polling + FastAPI on 127.0.0.1:8001 for pushes)
- [ ] `plutus-dashboard` (Streamlit, 8 tabs incl. Rejected Headlines panel)
- [ ] Reddit sentiment pipeline
- [ ] MF/FII data pipeline
- [ ] WhatsApp alerts
- [ ] End-to-end dry run + Cloudflare Tunnel
- [ ] 4 systemd units: `postgresql.service`, `plutus-main.service`, `plutus-bot.service`, `plutus-dashboard.service`

### Post-MVP
- [ ] Validate paper trading accuracy vs real market
- [ ] Tune strategy bundle weights from rolling 4-week performance
- [ ] (Optional) wire `nsepython` as a fallback OHLCV source if yfinance proves unreliable from OCI

---

## 14. Open Questions / Assumptions

| # | Item | Assumption Made |
|---|---|---|
| A2 | DeepSeek V4 Flash availability on OpenRouter | Confirmed; both fast + reason env vars point at it; swap reason model later if needed |
| A3 | Live trade execution | NOT in MVP; paper trading only until user validates |
| A4 | Intraday vs positional | System targets positional swing trades (3–10 days hold); no scalping |
| A5 | Telegram group vs private | Private bot (single user); can extend to group later |
| A6 | Domain | Use Cloudflare Tunnel free subdomain; add custom domain later |
| A7 | BSE vs NSE | NSE primary; BSE secondary where stock not listed on NSE |
| A8 | Seed universe refresh | Manual monthly refresh from NSE CSVs via `scripts/refresh_seed_universe.py` |
| A9 | F&O ban list freshness | Best-effort daily fetch; fall back to stale `data/fno_ban_list.txt` with logged warning |
| A10 | Symbol cache eviction | 5-min TTL only; cleared on `plutus-main` restart (acceptable for MVP) |

---

## 15. Verification Plan

1. **Data pipeline:**
   `python -c "from plutus.data.ohlcv import fetch_ohlcv; print(fetch_ohlcv('RELIANCE', days=90))"`
   → returns 90 rows of OHLCV
2. **Universe screener:**
   `python -c "from plutus.data.universe import build_universe; print(len(build_universe()))"`
   → returns ~150–200 symbols
3. **Backtest runner:**
   `python -c "from plutus.backtesting.runner import run_all_bundles; r = run_all_bundles('RELIANCE'); print(list(r.keys()))"`
   → prints 5 bundle keys including `composite`
4. **News prefilter:**
   `python -c "from plutus.data.news import prefilter_headlines; print(prefilter_headlines([{'headline':'SEBI bars promoter','source':'ET'}]))"`
   → returns the headline with `filter_status='kept'`
5. **Agent pipeline:**
   `python -c "from plutus.agents.graph import run_analysis; print(run_analysis('RELIANCE'))"`
   → returns recommendation JSON with `entry_mid`, `hold_days_min`, `hold_days_max`
6. **API (rate limit + cache):**
   `curl -X POST localhost:8000/analyze -H "X-API-Key: test" -d '{"symbol":"INFY"}'`
   → returns JSON with `cache_hit: false`, `rate_limit_remaining: <n>`; second call within 5 min → `cache_hit: true`
7. **Telegram:** Send `/stock HDFCBANK` in bot chat → receives formatted analysis within 25 seconds (or <1 sec on cache hit)
8. **/buy /confirm flow:** `/buy aggressive_momentum TATAMOTORS 790 50` → bot returns pre-trade check; `/confirm` → trade row inserted
9. **Weekly run:** Manually invoke `weekly_pipeline()` → verify `weekly_runs` row, `recommendations` rows with `entry_mid` populated, `reports/weekly/YYYY-MM-DD.md` written, Telegram summary received
10. **Monday revalidation:** Manually invoke `weekly_revalidate()` → verify `revalidation_note` + `revalidated_at` set on affected rows, no LLM calls in logs
11. **Outcome tracker:** Manually invoke `track_recommendation_outcomes()` on a 10-day-old run → verify `outcome`, `outcome_fill_price`, `outcome_exit_price`, `outcome_exit_date` populated; same-day collision resolves to `STOPPED`
12. **Rejected headlines:** Run `news_monitor()` with a stoplist-hit headline → verify row in `rejected_headlines` with `filter_status='stoplist'`
13. **Dashboard:** Open `localhost:8501` → all 8 tabs load; News Feed shows both Material Events and Rejected Headlines panels; History tab loads weekly markdown
14. **Bot internal push:** `curl -X POST http://127.0.0.1:8001/push/weekly-summary -d '{"run_id":1}'` → Telegram message delivered
15. **Systemd:** `systemctl status plutus-main plutus-bot plutus-dashboard postgresql` → all 4 active
