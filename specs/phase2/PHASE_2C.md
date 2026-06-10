# Phase 2C — Workflow Efficiency

**Priority:** P1/P2  
**Duration:** 7–10 days  
**Dependency:** Phase 2B complete (F5 paper trading, F7 symbol typeahead, F6 status bar)  
**Features:** F9, F10, F11

---

## 🔀 PARALLEL TASK GROUP: signals-deep-dive

### F9 — Signals Tab: Inline Stock Deep Dive

#### Problem
Signals tab shows a flat table. To research a stock, user must copy the symbol, switch to Strategy Lab or Analyze tab, paste, and run manually. This breaks the shortlisting workflow.

#### Technical Design

**Files to create/modify:**
- `src/plutus/dashboard/signals.py` — Expandable row component
- `src/plutus/dashboard/components.py` — `render_deep_dive_panel()` shared component
- `src/plutus/data/ohlcv.py` — Ensure chart data fetch is reusable

**Implementation Steps:**
1. Convert signals table rows to expandable sections (using `st.expander` or custom)
2. On row click/expand, render deep-dive panel:
   - 60-day candlestick chart with EMA21/EMA50 + volume
   - "Why BUY/WATCH" reasoning text (from agent pipeline output)
   - Sub-scores breakdown: Technical, Sentiment, Smart Money
   - Action buttons: Add to Watchlist, Log Paper Trade, Re-run Analysis
3. "Log Paper Trade" opens F5 form pre-filled with symbol + entry mid-price
4. "Re-run Analysis" triggers F2 analyze flow for that specific symbol
5. Chart renders from cached OHLCV data (no extra API call if recent)

**Data Sources:**
| Panel Element | Source |
|---------------|--------|
| Candlestick + EMA chart | `ohlcv` table (last 60 days for symbol) |
| Reasoning text | `recommendations` table → `reasoning` field |
| Sub-scores | `recommendations` table → `technical_score`, `sentiment_score`, `smart_money_score` |
| Entry/Target/Stop | `recommendations` table → price fields |

**Chart Spec:**
- Library: Plotly (already in dependencies)
- Type: Candlestick with EMA21 (blue), EMA50 (orange) overlays
- Volume bars below (separate subplot, 25% height)
- Entry zone highlighted (green band between entry_low and entry_high)
- Stop loss (red dashed line)
- Target lines (green dashed: T1, T2)

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f9_signals_deep_dive.py`

```python
class TestSignalsExpansion:
    def test_signals_table_rows_are_expandable(self):
        """Each signal row can be expanded inline"""
        
    def test_expanded_row_shows_chart(self):
        """Expanded signal shows candlestick chart"""
        
    def test_expanded_row_shows_reasoning(self):
        """Expanded signal shows 'Why BUY' reasoning text"""
        
    def test_expanded_row_shows_subscores(self):
        """Technical, Sentiment, Smart Money scores displayed"""
        
    def test_collapsed_by_default(self):
        """All rows start collapsed"""

class TestDeepDiveChart:
    def test_chart_has_candlestick_data(self):
        """Chart contains OHLC candlestick trace"""
        
    def test_chart_has_ema_overlays(self):
        """EMA21 and EMA50 lines present"""
        
    def test_chart_has_volume_subplot(self):
        """Volume bars rendered below price chart"""
        
    def test_chart_shows_entry_zone(self):
        """Green band between entry_low and entry_high"""
        
    def test_chart_shows_stop_and_targets(self):
        """Stop loss + T1/T2 horizontal lines present"""
        
    def test_chart_uses_cached_data(self):
        """No extra API call if OHLCV data < 1 hour old"""

class TestDeepDiveActions:
    def test_add_to_watchlist_button_present(self):
        """'Add to Watchlist' button visible in panel"""
        
    def test_log_paper_trade_prefills_form(self):
        """'Log Paper Trade' opens F5 form with symbol + price"""
        
    def test_rerun_analysis_triggers_analyze(self):
        """'Re-run Analysis' calls F2 analyze flow"""
        
    def test_watchlist_add_persists(self):
        """Adding to watchlist writes to DB"""
```

#### Success Criteria
- [ ] Signal row expands inline (no page navigation)
- [ ] Chart renders within 2s (cached data)
- [ ] Reasoning + sub-scores visible without scrolling
- [ ] "Log Paper Trade" pre-fills F5 form correctly
- [ ] "Re-run Analysis" triggers F2 flow for that symbol

---

## 🔀 PARALLEL TASK GROUP: editable-settings

### F10 — Settings Tab: Editable Trading Parameters

#### Problem
Trading parameters (capital, risk %, R:R ratio, max positions, hold days) are hard-coded in `.env`. Users must SSH to change them.

#### Technical Design

**Files to create/modify:**
- `src/plutus/dashboard/settings.py` — Editable form for trading parameters
- `src/plutus/config.py` — Add `update_config(key, value)` function
- `.env` — Target file for writes (single-user deployment)

**Implementation Steps:**
1. Read current values from config/env
2. Render editable form with current values as defaults
3. Validate input ranges on submit:
   - `INITIAL_CAPITAL`: ₹10,000 – ₹10,00,00,000
   - `MAX_RISK_PCT`: 1–10%
   - `MIN_RR_RATIO`: ≥ 1.0
   - `MAX_OPEN_POSITIONS_ADVISORY`: 1–20
   - `MAX_OPEN_POSITIONS_HARD`: 1–50
   - `HOLD_DAYS_MIN`: 1–30
   - `HOLD_DAYS_MAX`: 1–90
4. On save: write to `.env` file, show confirmation
5. Do NOT auto-restart services
6. Show warning: "Changes take effect on next analysis run"

**Security Note:** `.env` write is acceptable for single-user OCI deployment. If ever multi-user, this becomes a security issue (documented in PRD constraints).

**Form Layout:**
```
┌─────────────────────────────────────────────────────┐
│  Trading Parameters                    [Edit] [Save] │
│  Initial Capital:       ₹ [1,00,000    ]             │
│  Max Risk per Trade:    [  3  ] %                    │
│  Min Risk:Reward Ratio: [  1.5]                      │
│  Max Open Positions:    [ 4  ] (advisory)            │
│  Max Open Positions:    [ 10 ] (hard limit)          │
│  Hold Days:             [ 3  ] min  [ 10 ] max       │
│  [Save Changes]                                       │
│  ⚠️ Saving restarts the analysis engine.              │
└─────────────────────────────────────────────────────┘
```

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f10_settings.py`

```python
class TestConfigRead:
    def test_reads_current_values_from_env(self):
        """Form pre-fills with current .env values"""
        
    def test_missing_key_uses_default(self):
        """If key not in .env, uses hardcoded default"""

class TestConfigValidation:
    def test_capital_below_minimum_rejected(self):
        """₹9,999 → validation error"""
        
    def test_capital_above_maximum_rejected(self):
        """₹10,00,00,001 → validation error"""
        
    def test_risk_pct_below_1_rejected(self):
        """0.5% → validation error"""
        
    def test_risk_pct_above_10_rejected(self):
        """11% → validation error"""
        
    def test_rr_ratio_below_1_rejected(self):
        """0.8 → validation error"""
        
    def test_hold_days_min_greater_than_max_rejected(self):
        """min=15, max=10 → validation error"""
        
    def test_valid_values_pass(self):
        """All within range → validation passes"""

class TestConfigWrite:
    def test_save_writes_to_env_file(self):
        """Save updates .env file with new values"""
        
    def test_save_preserves_other_env_keys(self):
        """Writing trading params doesn't clobber DB_URL etc."""
        
    def test_save_shows_confirmation_message(self):
        """After save, user sees success message"""
        
    def test_save_does_not_restart_services(self):
        """No service restart triggered on save"""

class TestConfigSecurity:
    def test_only_whitelisted_keys_writable(self):
        """Cannot write arbitrary keys to .env"""
        
    def test_value_injection_prevented(self):
        """Newlines/quotes in values are escaped"""
```

#### Success Criteria
- [ ] Current settings displayed accurately from .env
- [ ] Validation prevents nonsensical values
- [ ] Save persists to .env without corrupting other keys
- [ ] Confirmation message shown after save
- [ ] No service disruption on save

---

## 🔀 PARALLEL TASK GROUP: news-actions

### F11 — News Feed: Symbol Filter + Alert-to-Action

#### Problem
News feed shows all events but user cannot filter to stocks they care about. No way to act on news (analyze, check portfolio) without manual copy-paste.

#### Technical Design

**Files to create/modify:**
- `src/plutus/dashboard/news.py` — Filter dropdown + action buttons per row
- `src/plutus/dashboard/components.py` — Reuse `symbol_input()` from F7 for filter

**Implementation Steps:**
1. Add symbol filter dropdown at top of News tab (populated from watchlist + portfolio holdings)
2. Filter news table by selected symbol(s) — multi-select
3. Add action buttons per news row:
   - 🔍 Analyze → triggers F2 analyze flow for that symbol
   - 👁 Add to Watchlist → adds symbol to watchlist
   - 💼 Check Portfolio → checks all portfolios for positions in that symbol
4. "Check Portfolio" shows inline result:
   - If holding: "⚠️ You hold {qty} × {symbol} in {portfolio} (entry ₹X, current ₹Y, unrealised ₹Z)"
   - If not holding: "No open positions in {symbol}"
5. Negative news + holding → show "Exit Position" shortcut (opens F5 SELL form pre-filled)

**Data Flow:**
```
News Feed loads → fetch material_events from DB
→ User selects filter: [RELIANCE, SUNPHARMA] (from watchlist)
→ Table filters to show only matching rows
→ User clicks "Check Portfolio" on SUNPHARMA negative news
→ Query portfolios for open SUNPHARMA positions
→ Show result inline with "Exit Position" action
```

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f11_news_actions.py`

```python
class TestNewsFilter:
    def test_filter_dropdown_populated_from_watchlist(self):
        """Filter options include watchlist symbols"""
        
    def test_filter_dropdown_includes_portfolio_holdings(self):
        """Filter options include symbols with open positions"""
        
    def test_filter_reduces_table_rows(self):
        """Selecting symbols shows only matching news"""
        
    def test_no_filter_shows_all(self):
        """Empty filter → all news shown"""
        
    def test_multi_select_works(self):
        """Selecting 2+ symbols shows union of matches"""

class TestNewsActionButtons:
    def test_analyze_button_present_per_row(self):
        """Each news row has 'Analyze' action"""
        
    def test_analyze_triggers_f2_flow(self):
        """Clicking analyze calls analyze pipeline for symbol"""
        
    def test_add_to_watchlist_persists(self):
        """'Add to Watchlist' writes symbol to watchlist table"""
        
    def test_check_portfolio_shows_position(self):
        """'Check Portfolio' for held symbol shows position details"""
        
    def test_check_portfolio_no_position(self):
        """'Check Portfolio' for unheld symbol shows 'No positions'"""

class TestNewsAlertToAction:
    def test_negative_news_with_holding_shows_exit(self):
        """Negative sentiment + open position → 'Exit Position' shortcut"""
        
    def test_exit_position_prefills_sell_form(self):
        """'Exit Position' opens F5 SELL form pre-filled"""
        
    def test_positive_news_no_exit_button(self):
        """Positive sentiment → no 'Exit Position' shown"""
```

#### Success Criteria
- [ ] Filter dropdown shows watchlist + portfolio symbols
- [ ] Filtering reduces table to selected symbols only
- [ ] "Analyze" button triggers F2 pipeline for that stock
- [ ] "Check Portfolio" shows position details inline
- [ ] Negative news + holding → "Exit Position" shortcut works

---

## Phase 2C — Execution Order

```
[Pre-requisite] Phase 2B complete (F5 paper trading, F7 typeahead, F6 status bar)
     ↓
[Parallel] F9 (signals deep dive) + F10 (editable settings) + F11 (news actions)
     ↓
[Sequential] Integration: F9 "Log Paper Trade" uses F5, F11 "Exit Position" uses F5 SELL flow
```

**Parallel Safety:**
- F9 owns `src/plutus/dashboard/signals.py` — no conflict
- F10 owns `src/plutus/dashboard/settings.py` + `src/plutus/config.py` — no conflict
- F11 owns `src/plutus/dashboard/news.py` — no conflict
- All three import from `components.py` (read-only) and `portfolio.py` (F5 form — call only, no modify)

All three features are fully independent and can be developed in parallel without merge conflicts.
