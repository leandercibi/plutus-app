# PRD: IndiaTradeAI — Agentic Stock Recommendation Engine

---

## 1. Context & Problem Statement

A retail trader with ₹1,00,000 INR capital wants to trade Indian equities (NSE/BSE) on a short-term basis (weekly horizon). The core problem: making informed buy/sell/hold decisions requires synthesising technical analysis, news sentiment, institutional (MF/FII) signals, and risk management simultaneously — a task that is cognitively overwhelming for a solo trader.

This system replaces manual research with an agentic pipeline powered by DeepSeek V3 (via OpenRouter), running 5 parallel trading strategy bundles, and exposing results through Telegram, a web dashboard, and an HTTP API (for Hermes agent integration).

**Intended outcome:** Every Sunday evening the user receives a prioritised, actionable recommendation list for the coming week. Intraday, breaking news on tracked stocks triggers instant alerts. On-demand stock queries can be answered in ~20 seconds from any surface (Telegram, Hermes, Dashboard).

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
Sunday 6:00 PM — Automated trigger (APScheduler)
  │
  ├── System screens all NSE stocks (~1800)
  │   Filter: Market cap > ₹500Cr, Avg daily volume > 5L shares,
  │           Not in F&O ban, Price ₹50–₹5000 (tradeable with 1L capital)
  │   Output: ~150–200 candidate stocks
  │
  ├── Run 5 strategy bundles (Backtrader, last 90 days)
  │   → Rank each candidate by backtested win rate this week
  │   → Strategy Selector picks best 2 bundles for current market regime
  │
  ├── Top 20 candidates enter LangGraph agent pipeline
  │   → Technical Agent (DeepSeek) — indicator confluence analysis
  │   → Sentiment Agent (DeepSeek) — news + Reddit scoring
  │   → Smart Money Agent (DeepSeek) — MF/FII signal
  │   → Risk Manager (DeepSeek) — position size, R:R check
  │   → Synthesizer (DeepSeek R1) — final verdict per stock
  │
  ├── Results saved to PostgreSQL
  │
  ├── Telegram message sent to user:
  │   "📊 Weekly Picks — 30 May 2026
  │    ✅ BUY (4 stocks): RELIANCE, TATAMOTORS, HDFCBANK, INFY
  │    ⏳ WATCH (3 stocks): WIPRO, SUNPHARMA, ONGC
  │    ❌ AVOID this week: Nifty trend weak — reduce new entries
  │    Reply /signals for details or /stock RELIANCE for deep dive"
  │
  └── Dashboard auto-refreshes with new recommendations
```

### Flow 2: On-Demand Stock Analysis (Telegram)
```
User sends to Telegram Bot: "TATAMOTORS" or "/stock TATAMOTORS"
  │
  ├── Bot acknowledges: "Analysing TATAMOTORS... ⏳ (~20 sec)"
  │
  ├── System triggers ad-hoc pipeline:
  │   → Fetch 90-day OHLCV data
  │   → Run all 5 strategy bundles
  │   → Run full agent pipeline (Technical + Sentiment + SmartMoney + Risk + Synthesizer)
  │
  └── Bot replies with structured report:
      "📈 TATAMOTORS — NSE | ₹789.50
       Recommendation: ✅ BUY (Confidence: 7.8/10)
       Entry Zone: ₹782–₹795
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
  │
  ├── API authenticates (API key in header)
  ├── Triggers same ad-hoc pipeline as Flow 2
  ├── Returns structured JSON (see Section 8)
  │
  └── Hermes reads JSON → answers user in natural language:
      "Based on current analysis, Infosys shows a moderate BUY signal
       with 6.9/10 confidence. Entry around ₹1,820–₹1,835, target
       ₹1,920, stop at ₹1,775. Three mutual funds are accumulating.
       Risk: 3.1% of your capital."
```

### Flow 4: News Alert (Intraday, Real-Time)
```
Hourly background job (APScheduler, every 60 min, market hours only)
  │
  ├── Fetches latest news for: watchlist stocks + current portfolio holdings
  │   Sources: NewsAPI, Google News RSS, Economic Times RSS, MoneyControl RSS
  │
  ├── DeepSeek classifies each headline:
  │   → Material event? (earnings surprise, regulatory action, promoter deal,
  │                       rating downgrade, block deal > ₹50Cr)
  │   → Sentiment: strongly positive / strongly negative / neutral
  │
  ├── If material event detected:
  │   → Telegram INSTANT alert:
  │     "🚨 NEWS ALERT — SUNPHARMA
  │      USFDA issues import alert on Halol plant
  │      Signal: ⬇️ SELL / EXIT if holding
  │      Current price: ₹1,234 | Expected impact: -3% to -7%
  │      /stock SUNPHARMA for full re-analysis"
  │   → WhatsApp backup alert (if enabled)
  │
  └── Non-material news → stored in DB, shown in dashboard feed only
```

### Flow 5: Mock Portfolio Management (Multi-Portfolio)
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
          Unrealised P&L: +₹880
          Current Value: ₹1,07,220
          Cash Available: ₹80,340
          
          /portfolio aggressive_momentum history — full trade log"

User sends: /buy aggressive_momentum TATAMOTORS 790 50
  → "✅ Logged: BUY 50 × TATAMOTORS @ ₹790 in 'aggressive_momentum'
      Capital used: ₹39,500 | Cash remaining: ₹40,840"

User sends: /sell aggressive_momentum TATAMOTORS 845 50
  → "✅ Logged: SELL 50 × TATAMOTORS @ ₹845 in 'aggressive_momentum'
      Profit: +₹2,750 (+6.96%) on this trade
      Portfolio realised P&L now: +₹9,090"

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
       Strategy Selected: Bundle 3 (Breakout) 68% weight
       
       BUY Signals (4 stocks):
       ┌─────────────────────────────────────────────────────┐
       │ RELIANCE | Score: 8.2 | Entry: 2375-2395 | T: 2480 │
       │ Reasoning: "Strong breakout from 6-week range...    │
       │ 3 MFs accumulating, FII net buyer ₹340Cr"          │
       ├─────────────────────────────────────────────────────┤
       │ TATAMOTORS | Score: 7.8 | Entry: 782-795 | T: 845  │
       │ Reasoning: "EV segment coverage positive, RSI 64..." │
       └─────────────────────────────────────────────────────┘
       
       Outcome tracking (auto-updated after 10 days):
       • RELIANCE: Hit Target 1 ✅ (+3.6%)
       • TATAMOTORS: Stopped out ❌ (-4.8%)"

Storage: Each weekly run saves a Markdown file:
  reports/weekly/2026-05-25.md    ← human-readable full report
  + DB row in weekly_runs table   ← for querying / charting
```

### Flow 7: Backtest & Strategy Comparison (Dashboard)
```
User opens Dashboard → navigates to "Strategy Lab" tab
  │
  ├── View: Table of all 5 strategy bundles
  │   Columns: Win Rate, Avg Return/Trade, Max Drawdown,
  │            Sharpe Ratio, Total Trades (90 days), Current Weight
  │
  ├── Chart: Equity curve for each bundle (overlaid)
  │
  ├── Trigger manual backtest:
  │   Select: Stock | Date range | Strategy bundle
  │   → Run → Show trade log + P&L chart
  │
  └── Paper trading feed: Every simulated trade logged with
      entry/exit/reason/outcome
```

### Flow 8: Dashboard Overview (Full View)
```
Dashboard tabs:
  1. 🏠 Home         — Weekly summary card, top picks at a glance
  2. 📊 Signals      — Full recommendation table, sortable by score
  3. 💼 Portfolio    — Paper positions, P&L chart, trade history
  4. 🧪 Strategy Lab — Backtest runner, strategy comparison
  5. 📰 News Feed    — All news events for tracked stocks, sentiment tags
  6. 👁 Watchlist    — Manage tracked stocks, per-stock mini-analysis
  7. 📋 History       — Past weekly reports, outcomes, searchable recommendation log
  8. ⚙️ Settings     — Risk %, capital, watchlist import, API key display
```

---

## 5. Feature Requirements

### P0 — Must Have (Week 1–2)
| # | Feature | Description |
|---|---|---|
| F1 | NSE Stock Screener | Filter 1800 NSE stocks to tradeable universe (~150-200) |
| F2 | 5 Strategy Bundles | Backtrader implementation of all 5 bundles |
| F3 | Weekly Pipeline | Full Sunday automated run with all agents |
| F4 | LangGraph Agents | Technical, Sentiment, Smart Money, Risk, Synthesizer |
| F5 | DeepSeek via OpenRouter | All LLM calls routed through OpenRouter API |
| F6 | On-Demand Analysis | `/stock SYMBOL` command triggers instant deep analysis |
| F7 | Telegram Bot | Alerts + commands (/signals /portfolio /stock /watch) |
| F8 | Multi-Portfolio Mock Trading | Named portfolios, buy/sell logging, per-portfolio P&L, win rate, trade history |
| F9 | News Monitor | Hourly job, material event detection, instant alerts |
| F10 | HTTP API `/analyze` | For Hermes agent tool calls (3 routes total) |
| F11 | Streamlit Dashboard | All 8 tabs as described in Flow 8 |
| F11a | Weekly History Store | Save each weekly run as `reports/weekly/YYYY-MM-DD.md` + DB row |
| F11b | Outcome Tracking | Auto-update recommendation outcomes after hold_days elapsed |
| F12 | Angel One Integration | Live price feed + historical data (once account ready) |

### P1 — Should Have (Week 2 / shortly after)
| # | Feature |
|---|---|
| F13 | Reddit Sentiment (PRAW) — r/IndianStreetBets, r/IndiaInvestments |
| F14 | MF Portfolio Tracking (AMFI + mftool) |
| F15 | FII/DII Daily Flow Signal |
| F16 | WhatsApp Alerts (CallMeBot) |
| F17 | Cloudflare Tunnel (public dashboard URL) |
| F18 | Multi-timeframe analysis (15m structure + 5m entry on Angel One live data) |

### P2 — Nice to Have (Post-MVP)
| # | Feature |
|---|---|
| F19 | Telegram inline keyboard (tap to add to watchlist, confirm paper trade) |
| F20 | Weekly performance email report (PDF via Streamlit export) |
| F21 | Strategy auto-weight tuning (weight bundles by last 4-week performance) |
| F22 | Real trade execution via Angel One SmartAPI (after paper trading validated) |

---

## 6. System Architecture

### Process Map
```
OCI A1.flex — 2 CPU / 12 GB RAM — Ubuntu 22.04 (ARM64)

Process 1: python main.py
  ├── FastAPI app (uvicorn, port 8000)
  │   ├── POST /analyze    — on-demand stock analysis
  │   ├── GET  /weekly     — latest weekly recommendations
  │   └── GET  /health     — liveness check
  ├── APScheduler
  │   ├── Cron: Sun 18:00  — weekly_pipeline()
  │   └── Cron: */60 min (Mon–Fri 09:00–16:00) — news_monitor()
  └── Telegram Bot (python-telegram-bot, polling mode)

Process 2: streamlit run dashboard.py --server.port 8501

Process 3: PostgreSQL 16 (systemd service)

Optional: Cloudflare Tunnel → exposes port 8501 publicly
```

### Folder Structure
```
indiatradeai/
├── main.py                        # entry point: FastAPI + scheduler + bot
├── config.py                      # all settings from env vars
├── requirements.txt
│
├── data/
│   ├── universe.py                # NSE stock screener, filter to tradeable list
│   ├── ohlcv.py                   # fetch historical + live OHLCV (yfinance / Angel One)
│   ├── news.py                    # NewsAPI + RSS fetcher + DeepSeek classifier
│   ├── reddit.py                  # PRAW sentiment scraper
│   └── smart_money.py             # AMFI mftool + NSE FII/DII data
│
├── strategies/
│   ├── base.py                    # BaseStrategy(bt.Strategy) with common utils
│   ├── bundle_trend.py            # EMA crossover + momentum + market structure
│   ├── bundle_reversal.py         # Bollinger + RSI + divergence + candlestick
│   ├── bundle_breakout.py         # Breakout + Opening Range + session filter
│   ├── bundle_smc.py              # FVG + Order Block + Liquidity Grab + S&D
│   └── bundle_composite.py        # Multi-signal: 3-of-5 agreement gate
│
├── backtesting/
│   ├── runner.py                  # run all 5 bundles, return ranked results
│   └── paper_trader.py            # simulate trades, track open positions + P&L
│
├── agents/
│   ├── graph.py                   # LangGraph StateGraph definition
│   ├── technical.py               # Technical Analyst agent node
│   ├── sentiment.py               # News + Reddit Sentiment agent node
│   ├── smart_money.py             # MF/FII Smart Money agent node
│   ├── risk_manager.py            # Position sizing + R:R validation node
│   ├── synthesizer.py             # Final verdict agent node (DeepSeek R1)
│   └── prompts.py                 # All system prompts in one place
│
├── alerts/
│   ├── telegram_bot.py            # Bot commands + push functions
│   │                              # /portfolio /buy /sell /history /stock /watch /signals
│   └── whatsapp.py                # CallMeBot HTTP push
│
├── api/
│   └── routes.py                  # FastAPI route handlers
│
├── db/
│   ├── models.py                  # SQLAlchemy ORM models
│   ├── session.py                 # DB connection + session factory
│   └── schema.sql                 # Initial schema (run once)
│
├── dashboard.py                   # Streamlit app (all 8 tabs)
│
└── reports/
    └── weekly/                    # YYYY-MM-DD.md — one file per weekly run
                                   # human-readable, git-friendly, analysable later
```

---

## 7. Database Schema

```sql
-- Weekly analysis runs (one row per weekly run)
weekly_runs (
  id, run_date, market_regime, nifty_trend,
  strategy_selected, stocks_screened, stocks_analysed,
  total_buy_signals, total_watch_signals,
  report_md_path,                                   -- path to reports/weekly/YYYY-MM-DD.md
  created_at
)

-- Per-stock recommendations (many rows per weekly_run)
recommendations (
  id, weekly_run_id, symbol, exchange, recommendation,
  confidence, entry_low, entry_high, target1, target2,
  stop_loss, rr_ratio, hold_days, strategy_used,
  technical_score, sentiment_score, smart_money_score,
  reasoning_text,
  outcome,                                          -- NULL until tracked; HIT_T1/HIT_T2/STOPPED/EXPIRED
  outcome_pct, outcome_tracked_at,
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

-- News events
news_events (
  id, symbol, headline, source, published_at,
  sentiment,                                        -- positive/negative/neutral
  is_material, alert_sent, created_at
)

-- Strategy backtest results (refreshed weekly)
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
    "strategy": "Bundle 3 + Bundle 1 (70% confluence)",
    "signals": {
      "technical": { "score": 7.5, "patterns": ["EMA crossover", "Volume breakout"] },
      "sentiment": { "score": 3.0, "summary": "Positive Jio coverage" },
      "smart_money": { "mf_accumulating": 3, "fii": "net_buyer" }
    },
    "risk_flags": [],
    "reasoning": "...",
    "analysis_time_sec": 18.4
  }

Response (422): symbol not found / not on NSE
Response (503): upstream data fetch failed
```

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
| Technical | deepseek/deepseek-chat (V3) | Fast, pattern interpretation |
| Sentiment | deepseek/deepseek-chat (V3) | Fast, text classification |
| Smart Money | deepseek/deepseek-chat (V3) | Fast, data interpretation |
| Risk Manager | deepseek/deepseek-chat (V3) | Deterministic math, light reasoning |
| Synthesizer | deepseek/deepseek-r1 | Complex multi-source synthesis |

### Cost Estimate
```
Per stock analysis (on-demand):   ~5 LLM calls → ~$0.02–0.05
Weekly run (20 stocks full pass): ~100 LLM calls → ~$0.50–1.00
Monthly total:                    ~$5–10
```

---

## 10. Strategy Bundle Summary

| Bundle | Core Logic | Key Indicators | Best Market Condition |
|---|---|---|---|
| 1: Trend | EMA crossover + momentum + volume | EMA 9/21/50, RSI > 55, Volume | Trending (bull/bear) |
| 2: Reversal | Oversold/overbought + divergence | Bollinger, RSI < 30/>70, MACD div | Ranging / exhausted trend |
| 3: Breakout | Consolidation escape + volume confirm | ATR, Volume ratio, Opening Range | Pre-breakout compression |
| 4: SMC | FVG fill + Order Block reaction + Liq Grab | FVG detection, volume, structure | All, especially volatile |
| 5: Composite | 3-of-4 bundle agreement required | All above | Low-noise, high-confidence only |

**Weekly Strategy Selection:**
- Run all 5 on last 90 days every Sunday
- Rank by Sharpe ratio for current week's market regime
- Top 2 bundles → primary signals; Bundle 5 always active as high-conviction filter
- Only stocks where Bundle 5 agrees → highest allocation

---

## 11. Data Sources

| Source | Data | Cost | Update Freq |
|---|---|---|---|
| yfinance (.NS / .BO) | OHLCV historical + intraday | Free | 15-min delay |
| Angel One SmartAPI | OHLCV live, WebSocket tick | Free (account needed) | Real-time |
| NewsAPI (free tier) | 100 req/day, headlines | Free | Hourly |
| Google News / ET / MC RSS | Unlimited headlines | Free | On-fetch |
| PRAW (Reddit API) | r/IndianStreetBets etc | Free, 60 req/min | Hourly |
| mftool (AMFI) | All MF portfolio holdings | Free, Python lib | Monthly |
| NSE website (FII/DII) | Institutional flow data | Free, scrape | Daily |
| NSE bulk deals | Large block trades | Free | End of day |

---

## 12. System Efficiency & Resource Usage

### Weekly Run Profile (Sunday 6 PM, ~25 min total)
```
Phase                         Time      CPU    RAM
──────────────────────────────────────────────────
NSE universe screen           2 min     15%    800 MB
Backtest 5 bundles × 200 stocks  12 min  85%   3.5 GB
Top 20 agent pipeline         8 min     30%    1.2 GB
DB writes + notification      1 min     5%     200 MB
──────────────────────────────────────────────────
Total                         ~25 min          Peak 4 GB
```

### On-Demand Analysis Profile (~20 sec)
```
Phase                         Time
──────────────────────────────────
Fetch OHLCV (90 days)         2 sec
Run 5 bundles (1 stock only)  3 sec
Fetch news                    2 sec
LangGraph agent pipeline      10–15 sec
DB write                      <1 sec
Total                         ~20 sec
```

### Always-On Resource Usage (idle)
```
Process 1 (FastAPI + Scheduler + Bot):  ~120 MB RAM
Process 2 (Streamlit dashboard):        ~150 MB RAM
PostgreSQL:                             ~200 MB RAM
Total idle:                             ~470 MB / 12 GB — very light
```

---

## 13. MVP Scope (2 Weeks)

### Week 1 Deliverables
- [ ] OCI environment setup (Python 3.11, PostgreSQL, venv)
- [ ] yfinance data pipeline + NSE screener
- [ ] All 5 strategy bundles (Backtrader)
- [ ] LangGraph agent pipeline with DeepSeek via OpenRouter
- [ ] Paper trading engine + DB schema
- [ ] News fetcher + DeepSeek classifier

### Week 2 Deliverables
- [ ] FastAPI (3 routes) + APScheduler + Telegram bot
- [ ] Streamlit dashboard (7 tabs)
- [ ] Reddit sentiment pipeline
- [ ] MF/FII data pipeline
- [ ] WhatsApp alerts
- [ ] End-to-end dry run + Cloudflare Tunnel

### Post-MVP (Angel One goes live)
- [ ] Swap yfinance → Angel One SmartAPI for live prices
- [ ] Enable real-time news monitoring (WebSocket feed)
- [ ] Validate paper trading accuracy vs real market
- [ ] Consider live execution (separate phase, explicit user consent per trade)

---

## 14. Open Questions / Assumptions

| # | Item | Assumption Made |
|---|---|---|
| A1 | Angel One API activation | 2–3 day lag; build with yfinance first |
| A2 | OpenRouter DeepSeek "V4" | Treat as V3 (`deepseek/deepseek-chat`); upgrade model ID when V4 available |
| A3 | Live trade execution | NOT in MVP; paper trading only until user validates |
| A4 | Intraday vs positional | System targets positional swing trades (3–10 days hold); no scalping |
| A5 | Telegram group vs private | Private bot (single user); can extend to group later |
| A6 | Domain | Use Cloudflare Tunnel free subdomain; add custom domain later |
| A7 | BSE vs NSE | NSE primary; BSE secondary where stock not listed on NSE |

---

## 15. Verification Plan

1. **Data pipeline:** `python -c "from data.ohlcv import fetch; print(fetch('RELIANCE', days=90))"` → returns 90 rows of OHLCV
2. **Backtest:** `python backtesting/runner.py --symbol RELIANCE --bundle trend` → prints trade log + win rate
3. **Agent pipeline:** `python -c "from agents.graph import run_analysis; print(run_analysis('RELIANCE'))"` → returns recommendation JSON
4. **API:** `curl -X POST localhost:8000/analyze -H "X-API-Key: test" -d '{"symbol":"INFY"}'` → returns JSON
5. **Telegram:** Send `/stock HDFCBANK` in bot chat → receives formatted analysis within 25 seconds
6. **Weekly run:** Manually invoke `weekly_pipeline()` → verify DB rows created + Telegram summary received
7. **Dashboard:** Open `localhost:8501` → all 7 tabs load, signals table populated, equity curve renders
8. **Paper trade:** Simulate BUY from Telegram command → appears in `/portfolio` with correct position size
