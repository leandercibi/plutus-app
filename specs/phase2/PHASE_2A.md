# Phase 2A — Fix What's Broken

**Priority:** P0 (Critical)  
**Duration:** 3–4 days  
**Dependency:** None — unblocks core usability  
**Features:** F1, F2, F3, F4

---

## 🔀 PARALLEL TASK GROUP: backtest-fix

### F1 — Fix Strategy Lab Backtest

#### Problem
Strategy Lab backtest returns statistically impossible results (Sharpe -93 on RELIANCE with Trend bundle, 90 days). The system shows no error when data is insufficient.

#### Root Cause Hypothesis
1. `fetch_ohlcv()` returns fewer than minimum bars needed for indicator warm-up (EMA50 needs ≥50 bars)
2. No guard in backtest runner validates minimum data length before running Cerebro
3. Result displays with no indication that data was insufficient

#### Technical Design

**Files to modify:**
- `src/plutus/data/ohlcv.py` — Add minimum-bar validation
- `src/plutus/backtesting/runner.py` — Add data-length guard, sanitize output
- `src/dashboard.py` → extract to `src/plutus/dashboard/strategy_lab.py` — Result display with error states

**Implementation Steps:**
1. Add `MIN_BARS_REQUIRED` constant (default: 60) to backtest runner
2. Add validation in `fetch_ohlcv()` return — attach metadata: `bars_fetched`, `bars_requested`
3. Guard in `runner.py`: if `bars < MIN_BARS_REQUIRED`, raise `InsufficientDataError` with diagnostic info
4. Handle the error in dashboard: show error card instead of impossible metrics
5. Add warning state: if bars < requested but ≥ MIN_BARS, show yellow warning
6. Sanitize Sharpe/Win Rate output: clamp to sane ranges, flag if outside [-5, +5]

**Data Flow:**
```
User submits (symbol, days, bundle)
→ fetch_ohlcv(symbol, days)
→ VALIDATE: bars >= MIN_BARS_REQUIRED (60)
  → FAIL: return InsufficientDataError("Only {n} bars retrieved, need {min}")
  → WARN: bars < days but >= MIN_BARS → proceed with warning flag
  → PASS: run backtest
→ runner.run(strategy_class, ohlcv_df)
→ VALIDATE output: Sharpe in [-5, +5], Win Rate in [0%, 100%], Trades >= 1
  → FAIL validation: flag as "suspect results" with diagnostic
→ Return BacktestResult(metrics, trade_log, equity_curve, warnings)
```

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f1_backtest.py`

```python
# --- Unit Tests ---

class TestOHLCVValidation:
    def test_fetch_returns_bar_count_metadata(self):
        """fetch_ohlcv result includes bars_fetched field"""
        
    def test_fetch_empty_returns_zero_bars(self):
        """When yfinance returns empty df, bars_fetched = 0"""
        
    def test_fetch_partial_returns_actual_count(self):
        """When yfinance returns 30/90 requested bars, metadata reflects 30"""

class TestBacktestRunner:
    def test_insufficient_bars_raises_error(self):
        """< 60 bars raises InsufficientDataError with message"""
        
    def test_exactly_min_bars_runs_successfully(self):
        """Exactly 60 bars runs without error"""
        
    def test_partial_bars_returns_warning(self):
        """70/90 bars runs but result.warnings is non-empty"""
    
    def test_sharpe_clamped_to_sane_range(self):
        """Sharpe outside [-5, +5] is flagged as suspect"""
        
    def test_zero_trades_returns_no_signal_result(self):
        """If strategy generates 0 trades, return NoSignalResult not division-by-zero"""
        
    def test_valid_backtest_returns_complete_metrics(self):
        """Happy path: returns win_rate, sharpe, total_trades, avg_return, max_drawdown"""
        
    def test_trade_log_contains_required_fields(self):
        """Each trade has: date, entry, exit, pnl, reason"""

class TestBacktestResultSanity:
    def test_win_rate_between_0_and_100(self):
        """Win rate is always 0-100%"""
        
    def test_total_trades_is_positive_integer(self):
        """total_trades >= 0 (integer)"""
        
    def test_reliance_trend_90d_produces_sane_sharpe(self):
        """Integration: RELIANCE Trend 90d → Sharpe in [-2, +3]"""
```

#### Success Criteria
- [ ] RELIANCE Trend 90d: Win Rate 30–70%, Sharpe -2 to +3, Trades ≥ 5
- [ ] Empty data returns error card (not Sharpe of -93)
- [ ] Partial data shows yellow warning with bar count
- [ ] Trade log table renders with all fields populated

---

## 🔀 PARALLEL TASK GROUP: analyze-button-fix

### F2 — Fix the Analyze Button: Feedback + Result Display

#### Problem
Clicking "Run /analyze" gives zero user feedback. Button appears broken. Result (if any) is raw JSON dump.

#### Technical Design

**Files to modify:**
- `src/dashboard.py` → extract to `src/plutus/dashboard/analyze.py` — Button state management + result card
- `src/plutus/api/routes.py` — Ensure `/analyze` returns structured response (may already be correct)

**Implementation Steps:**
1. Wrap analyze button in a state machine: `idle → loading → success | error`
2. Use `st.session_state["analyze_status"]` to track state across reruns
3. Show phased progress messages during loading (Fetching → Strategies → Agents)
4. On success: render structured result card (not JSON)
5. On error: render error card with actionable message
6. On cache hit: show immediately with "Cached" badge
7. Re-enable button after result/error

**Result Card Component:**
```
┌─────────────────────────────────────────────────────┐
│  {SYMBOL} — NSE              ₹{price} (15m delay)   │
│  ────────────────────────────────────────────────    │
│  Recommendation:  ✅ BUY / ⚠️ WATCH / ❌ AVOID      │
│  Confidence:      {score}/10  [{visual_bar}]         │
│  Entry Range:     ₹{low} – ₹{high}                  │
│  Targets:         T1: ₹{t1}  T2: ₹{t2}             │
│  Stop Loss:       ₹{sl}                             │
│  Risk:Reward:     {rr}                               │
│  Hold Period:     {days} days                        │
│  Strategy:        {bundle_name} ({n}/5 agree)        │
│  ────────────────────────────────────────────────    │
│  ▶ Reasoning (collapsed by default)                  │
│  ▶ Sub-scores: Technical | Sentiment | Smart Money   │
└─────────────────────────────────────────────────────┘
```

**Error States:**
| Condition | Display |
|-----------|---------|
| API unreachable | "⚠️ Analysis service not reachable. Check Settings." |
| Rate limit | "⏳ Rate limit reached. Retry in {n}s." |
| Timeout (>30s) | "⏱️ Analysis timed out. Try again or check logs." |
| Unknown error | "❌ Unexpected error: {msg}. Check backend logs." |

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f2_analyze.py`

```python
class TestAnalyzeButtonState:
    def test_initial_state_is_idle(self):
        """Button starts in idle state, enabled"""
        
    def test_click_transitions_to_loading(self):
        """After click, state becomes loading, button disabled"""
        
    def test_success_transitions_to_result(self):
        """Successful API call shows result card"""
        
    def test_error_transitions_to_error_state(self):
        """Failed API call shows error card, button re-enables"""
        
    def test_button_reenables_after_result(self):
        """Button is clickable again after success"""

class TestAnalyzeResultCard:
    def test_renders_recommendation_badge(self):
        """BUY/WATCH/AVOID shown with correct icon"""
        
    def test_renders_all_price_fields(self):
        """Entry range, targets, stop loss all present"""
        
    def test_renders_confidence_score(self):
        """Score shown as X/10 with visual bar"""
        
    def test_reasoning_collapsed_by_default(self):
        """Reasoning section is expandable, starts collapsed"""
        
    def test_cached_result_shows_badge(self):
        """Cache hit shows '♻️ Cached result' badge"""

class TestAnalyzeErrorHandling:
    def test_api_unreachable_shows_correct_message(self):
        """ConnectionError → specific error card"""
        
    def test_timeout_shows_retry_message(self):
        """TimeoutError → timeout-specific card"""
        
    def test_rate_limit_shows_countdown(self):
        """429 response → rate limit card with seconds"""
        
    def test_unknown_error_shows_generic_card(self):
        """Unexpected exception → generic error with details"""
```

#### Success Criteria
- [ ] Clicking Analyze shows spinner + multi-step progress within 2s
- [ ] Result appears as structured card, not raw JSON
- [ ] API unreachable → error card with actionable text
- [ ] Button re-enables after success or error (never stuck)

---

## 🔀 PARALLEL TASK GROUP: portfolio-creation

### F3 — Portfolio Creation UI on Dashboard

#### Problem
Portfolio creation is locked behind Telegram/terminal. Dashboard shows portfolios but cannot create them.

#### Technical Design

**Files to modify:**
- `src/dashboard.py` → extract to `src/plutus/dashboard/portfolio.py` — Creation form UI
- `src/plutus/db/models.py` — Verify Portfolio model has all needed fields
- `src/plutus/db/session.py` — Add `create_portfolio()` helper if not present

**Implementation Steps:**
1. Add empty state detection: if `portfolio_count == 0`, show creation form prominently
2. Build creation form: Name (text), Capital (number), Notes (optional text)
3. Add validation: name uniqueness, capital range (₹1,000–₹10,00,00,000), name format
4. On success: insert into DB, reload page to show new portfolio
5. On failure: inline error below offending field
6. If portfolios exist: show "+ Create New Portfolio" link that expands form

**Validation Rules:**
| Field | Rule |
|-------|------|
| Name | Required, alphanumeric + underscore/hyphen, max 40 chars, unique (case-insensitive) |
| Capital | Required, ₹1,000 – ₹10,00,00,000 |
| Notes | Optional, max 200 chars |

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f3_portfolio.py`

```python
class TestPortfolioValidation:
    def test_valid_name_accepted(self):
        """'aggressive_momentum' passes validation"""
        
    def test_empty_name_rejected(self):
        """Empty string fails with 'Name is required'"""
        
    def test_special_chars_rejected(self):
        """'my portfolio!' fails with format error"""
        
    def test_name_too_long_rejected(self):
        """41-char name fails with length error"""
        
    def test_duplicate_name_rejected(self):
        """Existing name (case-insensitive) fails"""
        
    def test_capital_below_minimum_rejected(self):
        """₹999 fails with 'Minimum capital is ₹1,000'"""
        
    def test_capital_above_maximum_rejected(self):
        """₹10,00,00,001 fails with maximum error"""
        
    def test_valid_capital_accepted(self):
        """₹1,00,000 passes validation"""

class TestPortfolioCreation:
    def test_create_portfolio_inserts_to_db(self):
        """Valid inputs create a row in portfolios table"""
        
    def test_created_portfolio_has_zero_balance_used(self):
        """New portfolio starts with 0 positions"""
        
    def test_empty_state_shows_creation_form(self):
        """No portfolios → creation form displayed prominently"""
        
    def test_existing_portfolios_shows_link(self):
        """With portfolios → '+ Create New Portfolio' link visible"""
```

#### Success Criteria
- [ ] User can create portfolio from dashboard without Telegram
- [ ] Validation errors shown inline below fields
- [ ] Created portfolio appears immediately in dropdown
- [ ] Empty state guides user to create first portfolio

---

## 🔀 PARALLEL TASK GROUP: run-pipeline

### F4 — "Run Analysis Now" Button on Home Tab

#### Problem
No manual trigger exists to run the analysis pipeline. Users must wait for Sunday automation or use terminal. The existing button gives no feedback.

#### Technical Design

**Files to modify:**
- `src/plutus/api/routes.py` — New `POST /pipeline/run` endpoint
- `src/dashboard.py` → extract to `src/plutus/dashboard/home.py` — Run button + progress log
- `src/plutus/api/routes.py` — Add `GET /pipeline/status` endpoint

**New API Endpoint:**
```python
@router.post("/pipeline/run")
async def trigger_pipeline(background_tasks: BackgroundTasks):
    """
    Trigger full analysis pipeline.
    Returns 409 if already running.
    Returns 202 with run_id on success.
    """
```

```python
@router.get("/pipeline/status/{run_id}")
async def pipeline_status(run_id: str):
    """
    Returns current step, progress %, log lines since last poll.
    """
```

**Implementation Steps:**
1. Create `POST /pipeline/run` endpoint with mutex check (is pipeline already running?)
2. Create `GET /pipeline/status/{run_id}` for polling progress
3. Store pipeline state in DB or file-based lock (`/tmp/plutus_pipeline.lock`)
4. Dashboard: confirmation dialog before triggering
5. Dashboard: live progress log via `st.empty()` + polling every 5s
6. On complete: auto-refresh page, re-enable button
7. On error: show last log line + error, don't lock button permanently

**Access Control:**
- Simple file-based lock to prevent concurrent runs
- No auth for now (single-user system)

**State Machine:**
```
idle → confirmed → running → complete | error
         ↓
       cancelled
```

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f4_pipeline.py`

```python
class TestPipelineEndpoint:
    def test_trigger_returns_202_with_run_id(self):
        """POST /pipeline/run → 202 + run_id"""
        
    def test_trigger_while_running_returns_409(self):
        """Second POST while running → 409 Conflict"""
        
    def test_status_returns_current_step(self):
        """GET /pipeline/status/{id} → step name + progress"""
        
    def test_status_unknown_run_returns_404(self):
        """GET /pipeline/status/invalid → 404"""
        
    def test_lock_released_on_completion(self):
        """After pipeline finishes, lock is released"""
        
    def test_lock_released_on_error(self):
        """If pipeline errors, lock is still released"""

class TestPipelineLock:
    def test_acquire_lock_succeeds_when_free(self):
        """Lock acquisition succeeds when no pipeline running"""
        
    def test_acquire_lock_fails_when_held(self):
        """Lock acquisition fails when pipeline in progress"""
        
    def test_stale_lock_is_cleared(self):
        """Lock older than 2 hours is treated as stale"""

class TestPipelineProgress:
    def test_progress_updates_written_to_store(self):
        """Pipeline steps write progress to queryable store"""
        
    def test_progress_log_returns_lines_since_offset(self):
        """Polling with offset returns only new log lines"""

class TestDashboardRunButton:
    def test_shows_last_run_and_next_run_times(self):
        """Header shows 'Last run: X | Next: Y'"""
        
    def test_confirmation_dialog_shown_on_click(self):
        """Click triggers confirmation before actual run"""
        
    def test_button_disabled_during_run(self):
        """Button shows 'Pipeline running...' while active"""
        
    def test_button_reenables_after_completion(self):
        """Button returns to idle after pipeline finishes"""
```

#### Success Criteria
- [ ] User can trigger full pipeline from dashboard
- [ ] Confirmation dialog shown with cost/time estimate
- [ ] Live progress log updates every ~10s
- [ ] Concurrent runs prevented (409 response)
- [ ] Button never gets permanently stuck
- [ ] Page auto-refreshes to show new results on completion

---

## Phase 2A — Shared Concerns

### Dashboard Module Extraction (Pre-requisite)

Before parallel work on F1–F4 begins, extract dashboard sections into helper modules to avoid merge conflicts:

```
src/plutus/dashboard/
├── __init__.py
├── strategy_lab.py    ← F1 owns this
├── analyze.py         ← F2 owns this
├── portfolio.py       ← F3 owns this
├── home.py            ← F4 owns this
└── components.py      ← Shared UI components (cards, badges, spinners)
```

`src/dashboard.py` becomes a thin router that imports and calls these modules.

**This extraction is a sequential pre-requisite before parallel tasks start.**

### Execution Order

```
[Sequential] Dashboard module extraction (1 task, ~2 hours)
     ↓
[Parallel] F1, F2, F3, F4 — each in their own module
     ↓
[Sequential] Integration test: all 4 features work together in dashboard
```
