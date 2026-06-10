# PRD — Plutus Phase 2: Dashboard Reliability & Trader Usability
**Version:** 1.0  
**Author:** Product Manager, Equities Desk  
**Date:** 02 June 2026  
**Status:** Approved for Implementation  
**Preceding Review:** `PM_REVIEW.md`  
**Builds On:** `specs/PRD.md` (Phase 1)

---

## 0. Why This PRD Exists

Phase 1 delivered a structurally correct system: 5 strategy bundles, 5 LangGraph agents, a Telegram bot, a FastAPI backend, and an 8-tab Streamlit dashboard. However, a live review of the deployed app on 02 June 2026 found the dashboard **unusable for its primary job** — shortlisting stocks — due to five critical gaps:

1. No manual trigger to run the analysis pipeline (Sunday-only automation)
2. The `Run /analyze` button gives zero user feedback and appears broken
3. Portfolio creation is locked behind Telegram/terminal — no dashboard UI
4. Strategy Lab backtest returns statistically impossible results (Sharpe -93 on RELIANCE)
5. Symbol input accepts any string with no validation — silent failures everywhere

This PRD addresses all five gaps in a phased, testable plan, then layers in the UX improvements that transform a functional tool into an efficient one.

---

## 1. Personas (Unchanged from Phase 1, Context Added)

**Primary User: Solo NSE Swing Trader**
- Capital: ₹1,00,000
- Session pattern: Reviews dashboard Sunday evening; checks signals Monday morning
- Device: Laptop primarily, mobile on commute
- Pain today: Opens the dashboard and sees nothing actionable
- Goal: Walk away from the dashboard in under 5 minutes with a ranked shortlist and at least one trade logged in paper portfolio

**Secondary User: The Operator (also the trader)**
- Needs to know: Is the system running? Did last week's signals perform? Is the pipeline healthy?
- Pain today: Has to SSH into the server or check Telegram to know system status

---

## 2. Phase Map

| Phase | Theme | Duration | Dependency |
|---|---|---|---|
| **Phase 2A** | Fix What's Broken | 3–4 days | None — unblock core usability |
| **Phase 2B** | Close the Dashboard Gaps | 5–7 days | Phase 2A complete |
| **Phase 2C** | Workflow Efficiency | 7–10 days | Phase 2B complete |
| **Phase 2D** | Trader Power Features | 10–14 days | Phase 2C complete |

---

---

# PHASE 2A — Fix What's Broken
**Goal:** Make the dashboard usable. A trader should be able to get signals and log a trade without touching Telegram or a terminal.  
**Exit Criteria:** Strategy Lab backtest on RELIANCE returns a sensible result. The Analyze flow shows feedback and a result. At least one paper portfolio can be created from the dashboard.

---

## F1 — Fix Strategy Lab Backtest (P0)

### Problem
Running a backtest for RELIANCE on the Trend bundle returns:
> `Win Rate 0.0% | Sharpe -93.375 | Trades 2`

A Sharpe ratio of -93 is not physically meaningful. Only 2 trades in a 90-day window for a liquid large-cap indicates the strategy is failing to generate signals — almost certainly because the OHLCV data fetch is returning empty or malformed data due to yfinance being blocked on the local/residential IP.

### Root Cause Hypothesis (to verify during implementation)
1. `fetch_ohlcv()` is returning fewer than the required minimum bars for indicator warm-up (EMA50 needs at least 50 bars; if yfinance returns 0–10 rows, no signals fire)
2. No guard in the backtest runner validates minimum data length before running Cerebro
3. The result is displayed with no indication that data was insufficient

### Expected Behaviour After Fix
- Backtest for RELIANCE (Trend, 90 days) returns: Win Rate in range 30–70%, Sharpe between -2 and +3, Trades ≥ 5
- If data fetch fails, the UI shows a clear error: "Could not fetch OHLCV data for RELIANCE. Retry during market hours or check yfinance connectivity."
- If fewer than 60 bars returned, show warning: "Only N bars of data available. Backtest results may be unreliable (need ≥60)."

### User Flow
```
User opens Strategy Lab tab
→ Enters symbol: RELIANCE
→ Sets Days: 90
→ Selects Bundle: trend
→ Clicks "Run"
→ Dashboard shows spinner: "Fetching OHLCV data…"
  → If data fetch fails:
     Shows error card: "Data unavailable for RELIANCE. [Reason]. Try: RELIANCE.NS format, or retry in 5 min."
  → If < 60 bars:
     Shows yellow warning: "Only 42 bars retrieved. Results below may be unreliable."
  → On success:
     Shows result card:
       Win Rate: 47.3%
       Sharpe Ratio: 0.82
       Total Trades: 11
       Avg Return/Trade: +1.4%
       Max Drawdown: -8.2%
     + Collapsible trade log table: [Date | Entry | Exit | P&L | Reason]
     + Mini P&L equity curve chart
```

### What Is NOT in Scope for F1
- Fixing yfinance connectivity (that's an infrastructure concern — deploy to OCI)
- Changing the strategy logic itself
- Adding new strategy bundles

---

## F2 — Fix the Analyze Button: Feedback + Result Display (P0)

### Problem
Clicking "🔄 Run /analyze for HDFCBANK" in the Watchlist tab (or Signals tab) produces no visible response. No spinner, no result, no error. The backend API at `127.0.0.1:8000` may not be running, but the user has no way to know this.

The PRD specifies a ~20–30 second LLM pipeline. A 30-second silent wait is indistinguishable from a crash.

### Expected Behaviour After Fix

**Happy path (API running, cache miss):**
```
User clicks "🔄 Run /analyze for HDFCBANK"
→ Button becomes disabled (greyed out, text changes to "Analysing…")
→ Progress message appears below button:
   "⏳ Fetching OHLCV data…"         (0–3s)
   "⏳ Running 5 strategy bundles…"  (3–8s)
   "⏳ Running agent pipeline…"      (8–25s)
     (sub-labels: Technical → Sentiment → Smart Money → Risk → Synthesizer)
→ Result card appears (see Result Card spec below)
→ Button re-enables
```

**Happy path (cache hit — < 100ms):**
```
User clicks "🔄 Run /analyze for HDFCBANK"
→ Result card appears immediately
→ Badge: "♻️ Cached result (< 5 min old)"
```

**Error path (API not reachable):**
```
User clicks "🔄 Run /analyze for HDFCBANK"
→ Error card: "⚠️ Analysis service is not reachable.
               The backend (plutus-main) may not be running.
               Check the Services section in ⚙️ Settings."
→ Button re-enables
```

**Error path (rate limit hit):**
```
→ Warning card: "⏳ Rate limit reached. You can run 30 analyses/hour.
                 Retry in Xs."
```

### Analyze Result Card Spec
The result should be a structured card, not a raw JSON dump:

```
┌─────────────────────────────────────────────────────────────────┐
│  HDFCBANK — NSE                          ₹820.45 (15m delay)   │
│  ──────────────────────────────────────────────────────────     │
│  Recommendation:  ✅ BUY          Confidence: 7.2 / 10         │
│                                                                   │
│  Entry Zone:   ₹815 – ₹825    (Mid: ₹820)                      │
│  Target 1:     ₹870           (+6.1%)                           │
│  Target 2:     ₹910           (+11.0%)                          │
│  Stop Loss:    ₹795           (-3.1%)                           │
│  Risk:Reward:  1:2.0                                             │
│  Hold:         5 – 8 trading days                               │
│                                                                   │
│  Signals:                                                         │
│   Technical   [████████░░] 7.5   EMA crossover, Volume breakout  │
│   Sentiment   [█████░░░░░] 5.0   Neutral — no major news        │
│   Smart Money [███████░░░] 7.0   3 MFs accumulating             │
│                                                                   │
│  Strategy: Bundle 3 (Breakout) + Bundle 1 (Trend)               │
│  ♻️ Cached · Rate limit: 27/30 remaining                        │
│                                                                   │
│  [ + Add to Watchlist ]  [ 📋 Log Paper Trade ]                 │
└─────────────────────────────────────────────────────────────────┘
```

### What Is NOT in Scope for F2
- Changing the agent pipeline logic
- Adding new agents
- Rate limit increase (that's a config change)

---

## F3 — Portfolio Creation UI on Dashboard (P0)

### Problem
Creating a mock portfolio requires either:
a) Sending `/portfolio new myport 100000` on Telegram
b) Running a Python script in the terminal

Neither is acceptable for a trader using the web dashboard. The Portfolio tab is completely dead until a portfolio exists.

### Expected Behaviour After Fix

```
User opens 💼 Portfolio tab
→ If no portfolios exist:
   [Empty state card]
   "No portfolios yet."
   ┌─────────────────────────────────────┐
   │  Create your first portfolio        │
   │  Name:     [________________]       │
   │  Capital:  [₹ ____________]         │
   │  Notes:    [________________]       │
   │            [  Create Portfolio  ]   │
   └─────────────────────────────────────┘
   
→ User fills in Name: "aggressive_momentum", Capital: 100000
→ Clicks "Create Portfolio"
→ Validation:
   - Name: required, alphanumeric + underscores/hyphens only, max 40 chars
   - Name must be unique (case-insensitive)
   - Capital: required, ₹1,000 – ₹10,00,00,000 (1 lakh minimum, 10 crore max)
→ On success: Portfolio is created in DB; page reloads to Portfolio view for new portfolio
→ On failure: Inline error below the offending field ("Name already exists", "Minimum capital is ₹1,000")

→ If portfolios already exist:
   Dropdown shows all portfolios
   Below dropdown: small "+ Create New Portfolio" link
   Clicking it expands the same creation form inline
```

### What Is NOT in Scope for F3
- Deleting a portfolio from the dashboard (too destructive — keep on Telegram)
- Renaming portfolios
- Portfolio-level strategy assignment

---

## F4 — "Run Analysis Now" Button on Home Tab (P0)

### Problem
The weekly pipeline runs automatically every Sunday at 18:00 IST. There is no way to trigger it manually from the dashboard. This means:
- A trader who wants fresh signals on a Wednesday cannot get them
- After OCI deployment, the operator cannot verify the pipeline works without waiting until Sunday
- During development and testing, every test requires a terminal SSH session

### Expected Behaviour After Fix

```
User opens 🏠 Home tab
→ Top-right of the header area shows:
   "Last run: Never  |  Next auto-run: Sun 18:00 IST  |  [▶ Run Analysis Now]"

→ User clicks [▶ Run Analysis Now]
→ Confirmation dialog:
   "This will run the full analysis pipeline (~25 minutes).
    It fetches data for ~200 stocks, runs 5 strategy bundles,
    and calls the LLM agent pipeline for the top 20 candidates.
    Estimated cost: ~$0.20–0.50 (LLM calls).
    Continue?"
   [ Cancel ]  [ Yes, Run Now ]

→ User clicks "Yes, Run Now"
→ Button becomes disabled: "⏳ Pipeline running…"
→ Live progress log appears (auto-scrolling):
   [10:32:01] Starting weekly analysis pipeline...
   [10:32:03] Universe screener: 504 stocks in seed CSV
   [10:32:45] Universe filtered: 187 tradeable stocks
   [10:34:12] Backtest complete: Bundle 1 (Trend) — 187 stocks
   [10:35:03] Backtest complete: Bundle 2 (Reversal) — 187 stocks
   ... (updates every ~10 seconds via st.empty() polling)
   [10:57:44] Top 20 candidates selected
   [10:58:22] Agent pipeline: RELIANCE — BUY (8.1/10)
   ...
   [11:02:31] ✅ Pipeline complete. 5 BUY, 7 WATCH signals generated.
              Telegram notification sent.
→ Page auto-refreshes to show new results
→ Button re-enables
```

**Error handling:**
- If pipeline is already running: button shows "Pipeline already running…" (disabled)
- If pipeline errors mid-run: shows last log line + error message; does not lock button permanently
- If API unreachable: "Cannot start pipeline — backend service is not running. Check ⚙️ Settings."

### Access Control
This button is available to all users (single-user system per PRD). If multi-user is ever added, this becomes admin-only.

### What Is NOT in Scope for F4
- Cancelling a running pipeline mid-execution
- Partial runs (e.g., "only run for watchlist stocks")
- Changing the scheduled Sunday run time from this button

---

---

# PHASE 2B — Close the Dashboard Gaps
**Goal:** Every tab has something useful even before the weekly pipeline runs. Paper trading works end-to-end from the dashboard.  
**Exit Criteria:** A new user can create a portfolio, log a paper trade, and view their P&L without opening Telegram.

---

## F5 — Paper Trading: Buy / Sell from Dashboard (P1)

### Problem
The PRD correctly defines Buy/Sell as Telegram-only flows with `/confirm` for safety. However the dashboard currently shows only a "Pre-trade Check" button. For a trader reviewing signals on the web, having to switch to Telegram to execute a paper trade is friction.

The dashboard should support paper trade logging natively, mirroring the Telegram bot's pre-trade check + confirm flow.

### User Flow: Log a Paper Trade (BUY)

```
User is in 💼 Portfolio tab, has selected "aggressive_momentum"
→ Scrolls to "Log Trade" section (replaces current "Pre-trade Check")
→ Fills in form:
   Symbol:      [RELIANCE      ] (validated against universe CSV + watchlist)
   Side:        [BUY ▼]
   Shares:      [42            ]
   Entry Price: [₹ 2390        ]
→ Clicks "Check Risk"
→ Pre-trade risk card appears:
   ┌────────────────────────────────────────────────┐
   │  Pre-Trade Check — BUY 42 × RELIANCE           │
   │  Capital required:  ₹1,00,380  (100.4%) ⚠️     │
   │  Risk (stop-based): ₹4,200     (4.2% of cap ✅) │
   │  Open positions after this trade: 1 (limit: 4) │
   │  R:R estimate: 1.8 (above min 1.5 ✅)           │
   │                                                  │
   │  ⚠️ Capital used exceeds available cash.         │
   │     Reduce shares to 41 or lower.               │
   └────────────────────────────────────────────────┘
→ User adjusts shares to 41
→ Clicks "Check Risk" again → All checks pass ✅
→ "Confirm Trade" button activates
→ User clicks "Confirm Trade"
→ Success toast: "✅ BUY 41 × RELIANCE @ ₹2,390 logged in aggressive_momentum"
→ Open Positions table updates immediately
```

### User Flow: Log a Paper Trade (SELL)

```
User is in 💼 Portfolio tab
→ Open Positions table shows RELIANCE: 41 shares, Entry ₹2,390, Current ₹2,445
→ "Sell" button appears in that row
→ User clicks Sell
→ Inline sell form expands in the row:
   Exit Price: [₹ 2445] (pre-filled with last price if available)
   Reason:     [TARGET ▼] (TARGET / STOP / MANUAL / SIGNAL)
→ Clicks "Confirm Sell"
→ Row moves to Trade History
→ Success toast: "✅ SELL 41 × RELIANCE @ ₹2,445. P&L: +₹2,255 (+2.3%)"
```

### Validation Rules (mirroring Telegram bot)
| Check | Pass | Warn | Block |
|---|---|---|---|
| Capital available | Trade ≤ available cash | | Trade > available cash → hard block |
| Open positions | ≤ 4 | 5–9 (advisory warning) | ≥ 10 (hard block) |
| Min R:R | ≥ 1.5 | | < 1.0 (hard block) |
| Max risk % | ≤ 3% | 3–5% (advisory warning) | > 5% (hard block) |
| Symbol exists | In universe or watchlist | Unknown symbol → warn | |

### What Is NOT in Scope for F5
- Short selling from the dashboard (SELL closes a long position only)
- Modifying an open trade's entry price after logging
- Live order execution (paper trading only, by design)

---

## F6 — Persistent System Status Bar (P1)

### Problem
A trader has no idea if the backend services are running, when the last analysis ran, or how many stocks are being watched — without navigating to the Settings tab. Every tab feels disconnected.

### Expected Behaviour

A fixed status bar appears at the very top of the dashboard, above the tab bar, on every tab:

```
📈 Plutus  |  Last run: 25 May 2026  |  Next run: Sun 08 Jun 18:00  |  Watching: 4 stocks  |  Bot: 🟢  |  API: 🟢  |  DB: 🟢
```

| Element | Source | Update Frequency |
|---|---|---|
| Last run date | `weekly_runs` table, latest row | On page load |
| Next run date | Calculated from `WEEKLY_RUN_DAY` + `WEEKLY_RUN_HOUR` settings | On page load |
| Watching N stocks | `watchlist` table count | On page load |
| Bot status | `systemctl is-active plutus-bot.service` | On page load (cached 60s) |
| API status | `GET /health` HTTP probe | On page load (cached 60s) |
| DB status | Quick `SELECT 1` query | On page load (cached 60s) |

**Colour coding:**
- 🟢 Green = active/reachable
- 🟡 Yellow = degraded (e.g., API slow > 2s)
- 🔴 Red = unreachable/stopped
- ⚪ Grey = unknown

If Bot or API is 🔴, all Analyze and Run pipeline buttons across the dashboard become disabled with tooltip: "Backend offline. Check ⚙️ Settings."

---

## F7 — Symbol Input: Validation and Typeahead (P1)

### Problem
Every symbol input on the dashboard (Signals deep dive, Strategy Lab, Watchlist add, Portfolio trade log) accepts free text with no validation. Entering "HDFC" (merged entity) instead of "HDFCBANK" or "TCS.NS" instead of "TCS" causes silent failures downstream.

### Expected Behaviour

All symbol inputs become a **searchable dropdown** backed by the `seed_universe.csv` (504 stocks) plus the user's current watchlist:

```
User types "HDFC" in any symbol field
→ Dropdown shows:
   HDFCBANK  — HDFC Bank Ltd (NSE)
   HDFC      — ⚠️ Delisted/merged — use HDFCBANK
   HDFCAMC   — HDFC Asset Management (NSE)
   HDFCLIFE  — HDFC Life Insurance (NSE)
→ User selects HDFCBANK
→ Field populates with "HDFCBANK"
```

**Validation rules:**
- Symbol must exist in universe CSV OR user's watchlist OR be validated via a quick yfinance check
- If symbol is unknown: yellow warning "Symbol not in universe. Analysis may fail. Proceed anyway?"
- If symbol is in F&O ban list (from `fno_ban_list.txt`): orange warning "SYMBOL is currently in F&O ban list. Cannot take fresh F&O positions."
- Symbols are always stored uppercase

---

## F8 — Strategy Lab: Show Bundle Comparison Table on First Load (P1)

### Problem
The PRD specifies the Strategy Lab's primary view as a 5-bundle comparison table (Win Rate, Sharpe, Avg Return, Max Drawdown, Total Trades). This table currently only populates after the first weekly pipeline run. New users see only an empty manual backtest form.

### Expected Behaviour

**When no weekly run data exists:**
```
Strategy Lab shows a placeholder table with the 5 bundles and their
*expected characteristics* (from specs), clearly labelled:
"No backtest data yet. These are theoretical characteristics.
 Run a manual backtest below or wait for the Sunday pipeline."

Bundle      | Expected Win Rate | Logic          | Best Regime
Trend       | 45–60%           | EMA crossover  | Trending
Reversal    | 40–55%           | RSI divergence | Ranging
Breakout    | 35–55%           | Volume escape  | Pre-breakout
SMC         | 40–60%           | Order blocks   | All
Composite   | 55–70%*          | 3-of-4 agree   | Low noise
*fewer signals, higher confidence
```

**When weekly run data exists:**
The real backtest comparison table populates (as specced in Phase 1).

**Manual backtest result (after F1 fix) should also show:**
- A mini equity curve chart (P&L over time)
- A collapsible trade log table (Date, Entry, Exit, P&L %, Reason)
- A comparison bar: "How this bundle performed vs. the other 4 on this stock over this period"

---

---

# PHASE 2C — Workflow Efficiency
**Goal:** A trader can complete the full shortlisting workflow — see signals, understand reasoning, chart the stock, check risk, and log a trade — without ever leaving the Signals tab.  
**Exit Criteria:** Average time from opening the dashboard to logging a paper trade is under 3 minutes.

---

## F9 — Signals Tab: Inline Stock Deep Dive (P1)

### Problem
The Signals tab shows a table but clicking a stock doesn't expand any detail. To see a chart, the user goes to Watchlist. To run analysis, the user clicks a separate button and gets a raw JSON dump. To log a trade, the user goes to Portfolio. This 3-tab, 5-step workflow kills efficiency.

### Expected Behaviour

Clicking any row in the Signals table **expands it inline** into a full deep-dive panel:

```
[ ✅ RELIANCE | Score 8.1 | Entry ₹2375–₹2395 | T1 ₹2480 | Stop ₹2320 | R:R 1.9 | Bundle 3+1 ]
  ↓ (expanded on click)
  ┌──────────────────────────────────────────────────────────────┐
  │  RELIANCE — 60-day Candlestick + EMA21/EMA50 + Volume        │
  │  [Chart renders here]                                         │
  │                                                               │
  │  Why BUY:                                                     │
  │  "Strong breakout from 6-week consolidation. EMA9 crossed    │
  │   EMA21 on 28 May with 2.3× average volume. RSI at 64 —      │
  │   bullish but not overbought. 3 MFs accumulating (₹340Cr     │
  │   net buy last 30d). Sentiment: positive (+3/5)."            │
  │                                                               │
  │  Sub-scores:  Technical 8.0  Sentiment 6.0  Smart Money 7.5  │
  │                                                               │
  │  [ + Add to Watchlist ]  [ 📋 Log Paper Trade ]              │
  │  [ 🔄 Re-run Analysis  ]                                     │
  └──────────────────────────────────────────────────────────────┘
```

Clicking "Log Paper Trade" opens the same pre-trade check form from F5, pre-filled with the stock symbol and entry mid-price from the recommendation.

---

## F10 — Settings Tab: Editable Trading Parameters (P2)

### Problem
Settings shows a JSON dump of `initial_capital`, `max_risk_pct`, `min_rr_ratio`. A trader cannot change these from the dashboard. They must edit `.env` and restart the service.

### Expected Behaviour

Trading Parameters section becomes an editable form:

```
┌─────────────────────────────────────────────────────┐
│  Trading Parameters                    [Edit] [Save] │
│                                                       │
│  Initial Capital:       ₹ [1,00,000    ]             │
│  Max Risk per Trade:    [  3  ] %                    │
│  Min Risk:Reward Ratio: [  1.5]                      │
│  Max Open Positions:    [ 4  ] (advisory)            │
│  Max Open Positions:    [ 10 ] (hard limit)          │
│  Hold Days:             [ 3  ] min  [ 10 ] max       │
│                                                       │
│  [Save Changes]                                       │
│  ⚠️ Saving restarts the analysis engine.              │
└─────────────────────────────────────────────────────┘
```

On Save:
1. Validate ranges (e.g., max_risk_pct between 1–10%, rr_ratio ≥ 1.0)
2. Write to `.env` file
3. Show confirmation: "Settings saved. Changes take effect on next analysis run."
4. Do NOT auto-restart services (too disruptive; user restarts manually or next pipeline run picks up new values)

### What Is NOT in Scope for F10
- Editing API keys from the dashboard (security risk)
- Editing scheduler times (cron schedules require service restart, not just env change)

---

## F11 — News Feed: Symbol Filter + Alert-to-Action (P2)

### Problem
The News Feed tab shows material events but provides no path to act on them. A trader seeing "SUNPHARMA — USFDA import alert" wants to immediately analyze the stock and check if they hold it.

### Expected Behaviour

```
News Feed tab:
→ Material Events table shows:
   [2026-06-02 10:30] SUNPHARMA | ⬇️ Negative | USFDA issues import alert...
   
→ Each row has action buttons:
   [ 🔍 Analyze ]  [ 👁 Add to Watchlist ]  [ 💼 Check Portfolio ]
   
→ "Check Portfolio" checks all portfolios for open SUNPHARMA positions
   and shows: "⚠️ You hold 50 × SUNPHARMA in aggressive_momentum (entry ₹1,200, current ₹1,150, unrealised -₹2,500)"
   with a direct "Exit Position" shortcut
```

Additionally, a **symbol filter dropdown** (not a text input) lets the user filter the news feed by their watchlist stocks with one click.

---

---

# PHASE 2D — Trader Power Features
**Goal:** The dashboard becomes a genuine decision-support system, not just a data display. A trader has confidence in the signals because they can trace the reasoning and back it up with historical performance.  
**Exit Criteria:** A trader can challenge any BUY signal with historical backtests and sentiment breakdown before deciding to act.

---

## F12 — Confidence Score Drill-Down (P2)

A stock's overall confidence score (e.g., 7.8/10) should expand on hover/click to show:

```
Overall: 7.8 / 10
├─ Technical:    8.0   "EMA crossover, Volume breakout, RSI 64"
├─ Sentiment:    6.0   "Positive (+3/5): EV push coverage"
└─ Smart Money:  7.5   "4 MFs accumulating, FII net buyer ₹340Cr"
```

This lets a trader understand *why* the signal was generated and make their own judgement on whether to trust it.

---

## F13 — Market Regime Badge (P2)

A persistent, colour-coded badge on every tab showing the current Nifty50 market regime:

- 📈 **BULLISH TRENDING** (green) — Nifty above EMA50, trending up
- 📊 **SIDEWAYS** (yellow) — Nifty within ±2% of EMA50
- 📉 **BEARISH TRENDING** (red) — Nifty below EMA50

Source: Derived from Nifty50 (`^NSEI`) OHLCV, same yfinance pipeline. Updated on page load.

Context tooltip: "Market regime affects strategy selection. In BULLISH TRENDING, Bundle 1 (Trend) and Bundle 3 (Breakout) are prioritised."

---

## F14 — Weekly History: Outcome Tracking Display (P2)

The History tab currently shows a list of weekly runs but outcomes (HIT_T1, HIT_T2, STOPPED, EXPIRED) are not visually meaningful. Add:

1. **Outcome badge colours:** HIT_T1/T2 = green, STOPPED = red, EXPIRED = grey, PENDING = yellow
2. **Hit rate gauge** per weekly run (e.g., "4 of 7 closed trades hit T1 — 57% win rate")
3. **P&L attribution chart**: For a given week, show which stocks contributed positive/negative P&L
4. **Best/Worst trade highlight**: "Best: TATAMOTORS +6.9% in 4 days | Worst: SUNPHARMA -4.8% (stopped)"

---

## F15 — Export: Signals to CSV (P2)

A single "Export to CSV" button on the Signals tab that downloads the current recommendation table as a CSV file. Columns: Symbol, Signal, Score, Entry Low, Entry Mid, Entry High, T1, T2, Stop Loss, R:R, Hold Days, Strategy, Reasoning.

Use case: Share the shortlist in a morning meeting or email.

---

---

## 3. What Is Explicitly OUT OF SCOPE for Phase 2

The following are NOT to be built in this phase, regardless of how useful they seem:

| Feature | Reason Out of Scope |
|---|---|
| Real money trading / broker API integration | Phase 1 PRD explicitly defers this until paper trading is validated |
| Mobile app (iOS/Android) | Requires separate tech stack; Phase 3+ |
| Multi-user access / auth | Single-user system by design (PRD A5) |
| Options / derivatives recommendations | NSE equities only per PRD A4 |
| Intraday / scalping signals | System targets 3–10 day swing trades per PRD A4 |
| Changing the LLM models | DeepSeek V4 Flash is fixed for Phase 1+2 |
| Cancelling a running pipeline mid-execution | Adds significant complexity; low value for a solo trader |
| TradingView chart embedding | Phase 3+ (requires paid TradingView plan) |
| WhatsApp alerts implementation | Phase 1 P1 backlog; not a dashboard feature |
| Deleting a portfolio from dashboard | Too destructive without undo; keep on Telegram only |
| Short selling from dashboard | Long-only for NSE swing trading in Phase 2 |

---

## 4. Technical Constraints & Assumptions

| Constraint | Detail |
|---|---|
| Stack unchanged | Streamlit + FastAPI + PostgreSQL + LangGraph. No new frameworks. |
| Single file dashboard | `src/dashboard.py` remains the dashboard entry point; refactor into helper modules if needed but entry point stays |
| No new API endpoints for Phase 2A/B | F1–F4 use existing `/analyze` and `/weekly` endpoints + direct DB reads. F5 (paper trading) may need a new `/paper-trade` endpoint on FastAPI — acceptable. |
| yfinance blocking | Acknowledged known issue. All Phase 2 features degrade gracefully if yfinance is blocked. No feature assumes live price is always available. |
| Pipeline trigger endpoint | F4 (Run Now button) requires a new authenticated POST endpoint: `POST /pipeline/run`. Must check if pipeline is already running before accepting. |
| Streamlit session state | Use `st.session_state` for the run-progress log in F4 to avoid re-running on page interactions. |
| No `.env` write from Streamlit in prod | F10 (editable settings) writes to `.env`. This is acceptable for a single-user OCI deployment but must be noted — if dashboard is ever multi-user, this becomes a security issue. |

---

## 5. Verification Plan

Each feature has a clear pass/fail test:

| Feature | Pass Criteria |
|---|---|
| F1 — Backtest fix | RELIANCE Trend 90d returns: Win Rate 30–70%, Sharpe -2 to +3, Trades ≥ 5 |
| F1 — Backtest error | Empty data returns an error card (not a Sharpe of -93) |
| F2 — Analyze feedback | Clicking Analyze shows a spinner and multi-step progress. Result appears as a structured card, not raw JSON. |
| F2 — Analyze error | API unreachable → error card with "check Settings" CTA |
| F3 — Portfolio creation | Form creates a portfolio; it appears in the dropdown; duplicate name shows error |
| F4 — Run Now | Clicking Run Now shows confirmation → progress log → results appear on completion |
| F4 — Already running | Clicking Run Now when pipeline is running shows "already running" (does not start a second run) |
| F5 — Paper trade buy | Buy form: passes validation → Confirm → trade appears in Open Positions |
| F5 — Paper trade sell | Sell button in Open Positions row → closes trade → appears in Trade History with P&L |
| F5 — Hard block | Buy where capital > available cash → blocked with explanation |
| F6 — Status bar | Status bar visible on all tabs; Bot/API/DB show 🟢/🔴 correctly |
| F7 — Symbol typeahead | Typing "HDFC" shows dropdown with HDFCBANK, HDFCAMC, HDFCLIFE |
| F8 — Strategy Lab empty state | No weekly data → placeholder table with theoretical characteristics shown |
| F9 — Inline deep dive | Clicking a Signals row expands chart + reasoning + sub-scores + action buttons |

---

## 6. Prioritised Feature List

| Priority | Feature | Phase | Effort | Impact |
|---|---|---|---|---|
| **P0** | F1 — Fix Backtest | 2A | Medium | Unblocks trust in signal engine |
| **P0** | F2 — Fix Analyze button | 2A | Small | Unblocks on-demand analysis |
| **P0** | F3 — Portfolio creation UI | 2A | Small | Unblocks paper trading |
| **P0** | F4 — Run Analysis Now button | 2A | Medium | Unblocks weekly signals |
| **P1** | F5 — Paper trading from dashboard | 2B | Large | Removes Telegram dependency |
| **P1** | F6 — Persistent status bar | 2B | Small | Orientation + trust |
| **P1** | F7 — Symbol typeahead | 2B | Small | Reduces silent failures |
| **P1** | F8 — Strategy Lab empty state | 2B | Small | First-time UX |
| **P1** | F9 — Signals inline deep dive | 2C | Medium | Core shortlisting workflow |
| **P2** | F10 — Editable settings | 2C | Medium | Power user quality of life |
| **P2** | F11 — News Feed action buttons | 2C | Medium | Alert-to-action workflow |
| **P2** | F12 — Score drill-down | 2D | Small | Signal transparency |
| **P2** | F13 — Market regime badge | 2D | Small | Context for all signals |
| **P2** | F14 — History outcome display | 2D | Medium | Performance accountability |
| **P2** | F15 — Export to CSV | 2D | Tiny | Shareability |

---

## 7. Success Metrics

After Phase 2 is complete, the following should be measurable:

| Metric | Target |
|---|---|
| Time from dashboard open → first actionable signal visible | < 30 seconds (with cached data) |
| Time from signal seen → paper trade logged | < 3 minutes (without Telegram) |
| Backtest Sharpe on RELIANCE (Trend, 90d) | Within -2 to +3 range |
| Analyze pipeline: user-visible feedback within | < 2 seconds of button click |
| Zero hard crashes or blank tab panels | 0 unhandled exceptions in production logs |
| % of PRD features implemented and visible in dashboard | > 90% |

---

*Document prepared by: PM, Equities Desk*  
*For implementation by: Engineering*  
*Review cycle: After each phase (2A, 2B, 2C, 2D) before proceeding to next*
