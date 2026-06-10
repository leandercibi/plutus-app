# Plutus — PM Product Review
**Reviewer:** Product Manager (Investment Banking, Equities Desk)  
**Review Date:** 02 June 2026  
**App URL:** https://sum-variable-individually-caroline.trycloudflare.com/  
**PRD Source:** `specs/PRD.md` + `specs/11_dashboard.md` + `DASHBOARD_USER_GUIDE.md`  
**Review Method:** Live app walkthrough (all 8 tabs), PRD gap analysis, interactive testing

---

## TL;DR

Plutus is a well-architected, ambitious tool for a solo NSE swing trader. The **backend design is solid** — 5 strategy bundles, a LangGraph agent pipeline, scheduled weekly runs, Telegram integration, and a clean API contract are all thoughtfully specced and built. However, **as a standalone dashboard product, it is not yet usable for stock shortlisting** because the weekly pipeline has not run, leaving every primary tab empty. The one interactive function tested (Strategy Lab backtest) returned a deeply suspicious result. The UX has structural gaps that will frustrate a non-technical user. With the data flowing and some UX fixes, this can be a genuinely powerful tool.

---

## 1. What's Working Well ✅

### 1.1 App Loads and All 8 Tabs Render
The Streamlit dashboard is accessible via Cloudflare Tunnel. All 8 tabs (Home, Signals, Portfolio, Strategy Lab, News Feed, Watchlist, History, Settings) load without crashing or throwing JavaScript errors. Navigation between tabs is snappy.

### 1.2 Tab Structure Matches the PRD
The PRD specifies exactly 8 tabs with specific purposes. All 8 are present and correctly labelled with intuitive emoji icons. The user can orient themselves quickly just by scanning the tab bar.

### 1.3 Watchlist Has a Live Chart
The Watchlist tab has HDFCBANK pre-populated with a 60-day candlestick chart overlaying EMA21 and EMA50. The chart renders correctly (price axis, date axis, legend). This is the only genuinely useful visual on the dashboard in its current state and shows what the product *can* look like when data flows.

### 1.4 Settings Tab is Clean and Trustworthy
The Settings tab correctly redacts all secrets (API keys, tokens, passwords shown as `"***"`). The config JSON gives a clear picture of the system's risk parameters at a glance:
- `initial_capital: 100000`
- `max_risk_pct` (configured)
- `min_rr_ratio: 1.5`
- `hold_days_default: "3–10"`
This is good — a trader can quickly verify the system is set up to match their risk appetite.

### 1.5 Strategy Lab Has a Working Backtest Runner
The manual backtest form (Symbol + Days + Bundle + Run button) is present and functional. Clicking Run actually executes and returns a result. This is the only end-to-end interactive feature that works without prior data.

### 1.6 Error Handling is Graceful, Not Crashy
Empty states show informative messages rather than blank screens or stack traces:
- "No weekly analysis yet. Next run: Sunday 18:00 IST."
- "No portfolios yet. Create one via Telegram: `/portfolio new myport 100000`"
- "No history yet."
- "Live price unavailable." (Watchlist)
The app never crashed during testing.

### 1.7 Security Posture is Sound
API key auth, redacted secrets in UI, loopback-only bot API (127.0.0.1:8001), no hardcoded credentials — all correct for a tool handling financial data.

---

## 2. What's Not Working / Blocking Usability 🚨

### 2.1 Zero Usable Shortlist Data — The Core Job-to-be-Done is Blocked
**This is the #1 blocker.** The entire value proposition of Plutus — a prioritised, actionable weekly stock shortlist — is invisible because the Sunday pipeline has not run. Every primary tab (Home, Signals, History) shows "No data yet." A user opening this app for the first time has nothing to act on.

**Impact:** The app cannot currently be used to shortlist stocks at all. It is a shell.

**Root cause:** The automated Sunday 18:00 IST pipeline hasn't triggered (or hasn't triggered successfully). There is no "Run Pipeline Now" button anywhere on the dashboard.

**PRD gap:** The PRD correctly mandates this automation, but the dashboard provides zero manual override for the operator. The `FINAL_SUMMARY.md` even notes you need to run `asyncio.run(weekly_pipeline())` from a terminal — that is not acceptable for a PM or trader to do.

### 2.2 Strategy Lab Backtest Returns Nonsensical Results
Running a backtest for RELIANCE on the Trend bundle returned:
> `Win Rate 0.0% | Sharpe -93.375 | Trades 2`

A Sharpe ratio of **-93** is not physically meaningful for any real trading strategy over a 90-day backtest on Reliance Industries, one of India's most liquid large-caps. Only 2 trades were generated. This indicates either:
- The strategy logic has a bug (signal generation failing to fire)
- The OHLCV data fetch is returning empty/corrupted data (confirmed by yfinance blocking issues)
- The backtest window is misconfigured

**Impact:** A trader who sees this result will immediately distrust the entire system. If the strategy engine is broken, the weekly pipeline's BUY/WATCH signals are also untrustworthy.

### 2.3 Live Price is Unavailable on Watchlist
HDFCBANK shows "Live price unavailable." The chart renders (likely from cached data) but the LTP metric fails. The `YFINANCE_ISSUES.md` acknowledges this as a known issue on local/residential IPs.

**Impact:** A key trust signal for a trader — "what is the stock trading at right now?" — is missing. The analyze button for HDFCBANK also produced no visible output when clicked (no spinner, no result, no error message displayed in the UI).

### 2.4 Analyze Button Gives No User Feedback
Clicking "🔄 Run /analyze for HDFCBANK" in the Watchlist tab produced no visible response in the page. There was no loading indicator, no result section, no error. Either:
- The backend API at `127.0.0.1:8000` is not running (likely, since the weekly pipeline hasn't run)
- Streamlit's built-in spinner is invisible in the Cloudflare-proxied context
- The result renders below the fold with no scroll cue

**Impact:** A user clicking Analyze has no idea if anything is happening. They will click again (triggering duplicate requests), assume the app is broken, or give up.

### 2.5 Portfolio Creation Requires Terminal Access
The Portfolio tab correctly shows "No portfolios yet" but the call-to-action is:
> "Create one via Telegram: `/portfolio new myport 100000`"

The `DASHBOARD_USER_GUIDE.md` further clarifies that creating a portfolio from the dashboard requires running a Python script in the terminal. This is completely unacceptable for any user who isn't a developer.

**Impact:** The Portfolio tab — which includes paper trading, P&L tracking, and equity curves — is entirely inaccessible without a separate channel (Telegram) or dev access.

### 2.6 The Dashboard Cannot Stand Alone — Telegram Dependency is a UX Smell
Critical user flows are split across Telegram and the dashboard in a way that isn't documented in the UI itself:
- Create portfolio → Telegram only
- Execute buy/sell trades → Telegram only (dashboard has a "Pre-trade Check" but no Buy/Sell buttons per the actual spec code)
- Trigger on-demand analysis → Dashboard button exists but requires a running backend
- Add to watchlist → Dashboard has this ✅

A first-time user opening the dashboard URL has no idea they need a Telegram bot running in parallel. There is no onboarding message, no "connect your Telegram" CTA, no explanation of the two-surface model.

---

## 3. UX: What's Intuitive vs. What's Not

### Intuitive ✅

| Element | Why it Works |
|---|---|
| Tab bar with emoji icons | Instant scanning — "📊 Signals" and "💼 Portfolio" are self-explanatory |
| Settings tab structure | Config JSON + redacted secrets + service status is exactly what a power user wants |
| Watchlist chart (EMA21/EMA50 overlay) | Standard TA view; a trader knows immediately what they're looking at |
| Signal filter (BUY/WATCH multiselect) | Spec-correct; a trader only wants to see actionable signals |
| Empty state messages with next steps | "No weekly analysis yet. Next run: Sunday 18:00 IST." is clear and not alarming |
| Score shown as a progress bar in Signals table | Visual confidence scoring at a glance — great for shortlisting |

### Not Intuitive ❌

| Element | Problem |
|---|---|
| No "Run Analysis Now" button | There is no manual trigger for the pipeline anywhere on the dashboard. A trader who misses Sunday and wants a fresh run is stuck. |
| "Create portfolio via Telegram" instruction | Users do not expect a web dashboard to delegate its own core feature to an external app with no link or QR code. |
| Analyze button with no loading state | Clicking a button and seeing nothing happen breaks every mental model a user has. A 30-second wait needs a progress indicator. |
| Strategy Lab shows only "Manual Backtest" when empty | PRD specifies a 5-bundle comparison table as the primary view. New users see only an empty form — the most important section (bundle comparison) is hidden until data exists. |
| Settings tab is a raw JSON dump | The Trading Parameters section dumps `initial_capital: 100000` as JSON. There are no edit controls. A trader wants to *change* their capital/risk — not read code. |
| History tab is empty with no CTA | "No history yet." — with no button to generate history or explanation of when it will appear (just "No history yet" with no time reference). |
| Backtest result appears in-line below the form | After clicking Run, the result `Win Rate 0.0% | Sharpe -93.375` appears as a small badge with no context, no chart, no trade log. The PRD spec says it should show "trade log + P&L chart". |
| No breadcrumbs or current-state summary | The app has no persistent header showing "Last run: —" or "Watching 1 stock". A user switching tabs has to re-orient each time. |
| "Promote keyword" button in News Feed | This button generates YAML for the developer to manually add to a config file. This is an internal dev tool exposed directly in the production UI. |
| No symbol search / typeahead | The Symbol text input requires knowing the exact NSE ticker. No search, no autocomplete, no validation. Entering "HDFC" instead of "HDFCBANK" silently fails. |

---

## 4. PRD vs. Reality — Gap Analysis

| PRD Feature | Status | Notes |
|---|---|---|
| 8 dashboard tabs | ✅ Present | All tabs load |
| Home: Weekly summary card with top picks | ❌ Empty | Pipeline not run |
| Signals: Full sortable recommendation table | ❌ Empty | No data |
| Signals: Score as ProgressColumn | ✅ Specced correctly | Works once data present |
| Signals: Deep Dive chart + analyze button | ⚠️ Partial | Analyze button unresponsive |
| Portfolio: Multi-portfolio dropdown | ❌ Blocked | Requires Telegram to create |
| Portfolio: Equity curve overlay | ❌ No data | |
| Portfolio: Pre-trade check button | ✅ Present | Untested (no portfolio) |
| Strategy Lab: 5-bundle comparison table | ❌ Missing | Only manual backtest form shown; table requires DB data from weekly run |
| Strategy Lab: Equity curve per bundle | ❌ Missing | Same dependency |
| Strategy Lab: Manual backtest trigger | ✅ Present | Returns nonsensical results |
| News Feed: Material Events section | ✅ Present | Empty (news job not run) |
| News Feed: Rejected Headlines with "Promote keyword" | ✅ Present | Dev-facing tool exposed in prod UI |
| Watchlist: Add/remove + chart | ✅ Working | Chart renders, live price fails |
| Watchlist: Analyze per symbol | ⚠️ Button present | No visible output |
| History: Weekly runs table with quarter/month filter | ✅ Specced | Empty |
| Settings: Redacted env display | ✅ Working | Clean |
| Settings: Service status | ⚠️ Buttons rendered but unreadable | Three buttons with no labels visible in accessibility tree |
| Weekly pipeline: Sunday 18:00 IST | ⚠️ Discrepancy | PRD says 18:00 IST; FINAL_SUMMARY says 21:00 IST |
| Monday revalidation | ✅ Specced | Untestable (no data) |
| yfinance live price | ❌ Blocked locally | Documented known issue |

---

## 5. Can I Use This to Shortlist Stocks Efficiently?

**Today: No.**

The honest answer is that the app cannot be used for its primary job today because:
1. No weekly analysis has run, so there are no BUY/WATCH signals to review
2. The on-demand Analyze feature is unresponsive
3. The only backtest result returned is statistically impossible

**After the pipeline runs: Possibly, with caveats.**

Once data is populated, the Signals tab has the right bones — a sortable table with score (as a progress bar), entry zone, targets, stop loss, R:R, and strategy used. That is genuinely useful for shortlisting. The PRD's vision of "4 BUY signals with entry/target/stop in one view" is exactly what a trader needs.

However, the workflow to go from signal → trade is friction-heavy:
1. See a BUY signal in the Signals tab
2. Switch to Watchlist to get a chart (manual action, no link)
3. Run Analyze (30-second wait, no feedback)
4. Go to Telegram to execute a paper trade
5. Come back to Portfolio tab to see it

That's 5 steps across 2 apps. A Bloomberg terminal does this in 2 clicks.

---

## 6. Good-to-Have Recommendations (Prioritised)

### P0 — Must Fix Before This is Usable

| # | Recommendation |
|---|---|
| G1 | **Add a "Run Analysis Now" button** on the Home tab (admin-gated or confirmation dialog). Without this, the dashboard is useless until Sunday. |
| G2 | **Fix the Strategy Lab backtest** — investigate why RELIANCE returns 0% win rate / Sharpe -93. This destroys trust in the entire signal engine. |
| G3 | **Add loading state to the Analyze button** — show a spinner + "Running 5 agents, ~30 seconds…" message on click. |
| G4 | **Add portfolio creation to the dashboard UI** — a simple form: Portfolio Name + Initial Capital + Create. Remove the Telegram/terminal dependency for this. |

### P1 — High Value UX Improvements

| # | Recommendation |
|---|---|
| G5 | **Persistent status bar** at top of every tab: "Last run: — | Next run: Sun 18:00 | Watching: 1 stock | Open positions: 0". |
| G6 | **Symbol search with validation** — typeahead or dropdown from the universe CSV. Reject invalid symbols with a clear message before firing an API call. |
| G7 | **Link Signals → Chart → Trade** — clicking a stock in the Signals table should expand its chart inline (EMA + volume). Add "Add to Watchlist" and "Log Paper Trade" buttons right there, not across tabs. |
| G8 | **Settings tab: make Trading Parameters editable** — sliders for `max_risk_pct`, `initial_capital`, and `min_rr_ratio` instead of a JSON dump. Write to `.env` on save. |
| G9 | **Remove "Promote keyword" from the News Feed tab** — this is a developer tool. Move it to Settings or remove entirely from the user-facing UI. |
| G10 | **Onboarding banner** — on first load (no data), show a card: "Welcome to Plutus. Here's how to get started: 1. Connect Telegram bot 2. Wait for Sunday pipeline or click Run Now 3. Review BUY signals." |

### P2 — Nice-to-Have for Investment Banking Context

| # | Recommendation |
|---|---|
| G11 | **Export to CSV/PDF** — Signals table should be exportable. Traders need to share shortlists in morning meetings. |
| G12 | **Confidence score breakdown** — clicking a stock's score should expand to show Technical (7.2) + Sentiment (3.0) + Smart Money (4.0) sub-scores. The composite score alone doesn't help a trader challenge the system. |
| G13 | **Market regime indicator** — show current Nifty50 trend (Bullish/Bearish/Sideways) as a persistent badge. This contextualises every signal. |
| G14 | **Mobile-responsive layout** — Streamlit's default layout is not mobile-friendly. Traders check signals on phones during commute. |
| G15 | **Telegram ↔ Dashboard sync indicator** — show "Bot: Online ✅ / Offline ❌" in the header so the user knows if alerts are active. |
| G16 | **Real-time price updates (WebSocket)** — the 15-minute yfinance delay is fine for swing trading but should be clearly labelled everywhere (e.g., "LTP ₹840 (15m delay)"). |

---

## 7. Notable PRD Inconsistencies Found

1. **Weekly run time mismatch:** PRD (`specs/PRD.md`) states Sunday 18:00 IST. `FINAL_SUMMARY.md` states Sunday 21:00 IST. Needs to be reconciled — both cannot be correct.

2. **Strategy Lab described as "read-only" in user guide but has a manual trigger in the spec:** `DASHBOARD_USER_GUIDE.md` says "Buttons: None (read-only)" for Strategy Lab. The actual spec (`specs/11_dashboard.md`) and the live app both have a manual backtest form. The user guide is stale/wrong.

3. **Portfolio tab: Buy/Sell buttons in user guide vs. spec:** The user guide describes dedicated Buy/Sell buttons on the Portfolio tab. The actual dashboard spec only has a "Pre-trade Check" button — buying/selling is Telegram-only per the PRD. This misalignment will confuse users who read the guide.

4. **"Production-ready" certification vs. empty dashboard:** `FINAL_SUMMARY.md` certifies the app as "PRODUCTION-READY" with "Zero runtime errors." The live app has a broken backtest (Sharpe -93), unresponsive analyze button, and zero data. The certification was likely done against a local environment with different conditions, not the actual deployed state.

5. **82.6% test pass rate presented as success:** 195 tests, 161 passing means **34 tests are failing**. For a trading signal system where accuracy matters, 17.4% test failure is a risk flag, not a green light.

---

## 8. Summary Scorecard

| Dimension | Score | Notes |
|---|---|---|
| **Architecture & Design** | 8/10 | Thoughtfully specced, clean separation of concerns, good data model |
| **Dashboard Functionality (today)** | 2/10 | Core value prop (signals) entirely empty; backtest broken |
| **UX Intuitiveness** | 4/10 | Tab structure good; empty states, no feedback, Telegram dependency hurt badly |
| **PRD Fidelity** | 5/10 | Structure correct, data and interactivity gaps large |
| **Trust / Data Quality** | 3/10 | Backtest returning Sharpe -93 on RELIANCE is a serious red flag |
| **Stock Shortlisting Utility (today)** | 1/10 | Cannot be used; no signals exist |
| **Stock Shortlisting Utility (post-pipeline run)** | 6/10 | Signals tab will be usable; workflow is fragmented |

---

*Review conducted by: PM (Investment Banking, Equities Desk)*  
*Do not distribute externally. For internal product review only.*
