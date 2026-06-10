# Phase 2B — Close the Dashboard Gaps

**Priority:** P1  
**Duration:** 5–7 days  
**Dependency:** Phase 2A complete (dashboard module extraction, F3 portfolio creation exists)  
**Features:** F5, F6, F7, F8

---

## 🔀 PARALLEL TASK GROUP: paper-trading

### F5 — Paper Trading: Buy / Sell from Dashboard

#### Problem
Paper trading is only available via Telegram bot. Dashboard users cannot log trades without switching to a different interface.

#### Technical Design

**Files to create/modify:**
- `src/plutus/api/routes.py` — New `POST /paper-trade` endpoint
- `src/plutus/dashboard/portfolio.py` — Trade form + pre-trade risk check UI
- `src/plutus/backtesting/paper_trader.py` — Extend with validation logic (may already exist)
- `src/plutus/db/models.py` — Verify PaperTrade model exists

**New API Endpoint:**
```python
@router.post("/paper-trade")
async def log_paper_trade(trade: PaperTradeRequest):
    """
    Log a paper trade (BUY or SELL).
    Runs pre-trade risk check before confirming.
    Returns 422 if validation fails (hard blocks).
    Returns 200 with warnings for advisory checks.
    """

@router.post("/paper-trade/risk-check")
async def pre_trade_risk_check(trade: PaperTradeRequest):
    """
    Dry-run risk check without executing.
    Returns pass/warn/block status for each rule.
    """
```

**Implementation Steps:**
1. Create `PaperTradeRequest` schema: symbol, side (BUY/SELL), shares, entry_price, portfolio_id
2. Implement risk check engine (mirrors Telegram bot logic):
   - Capital available check
   - Open positions count (advisory ≤4, warn 5–9, block ≥10)
   - Min R:R check (≥1.5 pass, <1.0 block)
   - Max risk % check (≤3% pass, 3–5% warn, >5% block)
   - Symbol existence check
3. Build trade form in dashboard: Symbol (uses F7 typeahead), Side, Shares, Entry Price
4. "Check Risk" button → shows pre-trade risk card
5. "Confirm Trade" button → only active when no hard blocks
6. SELL flow: dropdown of open positions, auto-fills entry data, calculates P&L
7. On success: update positions table immediately

**Validation Rules:**
| Check | Pass | Warn | Block |
|-------|------|------|-------|
| Capital available | Trade ≤ available cash | — | Trade > available cash |
| Open positions | ≤ 4 | 5–9 (advisory) | ≥ 10 |
| Min R:R | ≥ 1.5 | — | < 1.0 |
| Max risk % | ≤ 3% | 3–5% (advisory) | > 5% |
| Symbol exists | In universe or watchlist | Unknown → warn | — |

**SELL Flow:**
```
User selects portfolio → sees Open Positions table
→ Clicks "Sell" on a position row
→ Form pre-fills: Symbol, Shares (full position), Side=SELL
→ User enters Exit Price
→ P&L calculated: (exit - entry) × shares
→ Clicks "Confirm Sell"
→ Position moves to Closed Trades
```

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f5_paper_trading.py`

```python
class TestRiskCheck:
    def test_capital_sufficient_passes(self):
        """Trade cost < available capital → pass"""
        
    def test_capital_insufficient_blocks(self):
        """Trade cost > available capital → hard block"""
        
    def test_positions_under_4_passes(self):
        """≤4 open positions → pass"""
        
    def test_positions_5_to_9_warns(self):
        """5-9 open positions → advisory warning"""
        
    def test_positions_10_plus_blocks(self):
        """≥10 open positions → hard block"""
        
    def test_rr_above_1_5_passes(self):
        """R:R ≥ 1.5 → pass"""
        
    def test_rr_below_1_0_blocks(self):
        """R:R < 1.0 → hard block"""
        
    def test_risk_pct_under_3_passes(self):
        """Risk ≤ 3% of capital → pass"""
        
    def test_risk_pct_3_to_5_warns(self):
        """Risk 3-5% → advisory warning"""
        
    def test_risk_pct_above_5_blocks(self):
        """Risk > 5% → hard block"""
        
    def test_unknown_symbol_warns(self):
        """Symbol not in universe → warning (not block)"""

class TestPaperTradeEndpoint:
    def test_buy_creates_position(self):
        """POST /paper-trade BUY → creates open position in DB"""
        
    def test_sell_closes_position(self):
        """POST /paper-trade SELL → moves to closed, calculates P&L"""
        
    def test_invalid_trade_returns_422(self):
        """Hard-block trade → 422 with reasons"""
        
    def test_sell_nonexistent_position_returns_404(self):
        """SELL on symbol not held → 404"""
        
    def test_sell_more_than_held_returns_422(self):
        """SELL 100 shares when holding 50 → 422"""

class TestPaperTradeUI:
    def test_buy_form_shows_all_fields(self):
        """Symbol, Side, Shares, Entry Price all present"""
        
    def test_risk_check_renders_card(self):
        """'Check Risk' click renders pre-trade risk card"""
        
    def test_confirm_disabled_on_hard_block(self):
        """'Confirm Trade' button disabled when hard block exists"""
        
    def test_sell_prefills_from_position(self):
        """Clicking sell on a position pre-fills the form"""
        
    def test_success_toast_on_trade(self):
        """Confirmed trade shows success message"""
        
    def test_positions_table_updates_after_trade(self):
        """Open positions table reflects new trade immediately"""
```

#### Success Criteria
- [ ] BUY trade logged from dashboard without Telegram
- [ ] SELL trade closes position and shows P&L
- [ ] Risk check prevents capital overallocation (hard block)
- [ ] Advisory warnings shown but don't prevent trade
- [ ] Validation mirrors Telegram bot behavior exactly
- [ ] Time from signal → trade < 3 minutes

---

## 🔀 PARALLEL TASK GROUP: status-bar

### F6 — Persistent System Status Bar

#### Problem
Users have no visibility into whether backend services are running. Buttons fail silently when API/bot is down.

#### Technical Design

**Files to create/modify:**
- `src/plutus/dashboard/components.py` — `render_status_bar()` component
- `src/plutus/dashboard/__init__.py` — Import and call on every page
- `src/plutus/api/routes.py` — Ensure `GET /health` exists

**Implementation Steps:**
1. Create `render_status_bar()` Streamlit component
2. Probe health checks on page load (cached 60s):
   - API: `GET /health` → 🟢/🔴
   - DB: `SELECT 1` → 🟢/🔴
   - Bot: `systemctl is-active plutus-bot.service` or process check → 🟢/🔴
3. Show last run date (from `weekly_runs` table)
4. Show next run date (calculated from settings)
5. Show watchlist count
6. Color coding: 🟢 active, 🟡 degraded (>2s), 🔴 down, ⚪ unknown
7. If API/Bot is 🔴: disable all Analyze/Run buttons across dashboard

**Status Bar Layout:**
```
📈 Plutus | Last run: 25 May 2026 | Next: Sun 08 Jun 18:00 | Watching: 4 | Bot: 🟢 | API: 🟢 | DB: 🟢
```

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f6_status_bar.py`

```python
class TestHealthChecks:
    def test_api_health_returns_green_when_up(self):
        """GET /health success → status 'up'"""
        
    def test_api_health_returns_red_on_connection_error(self):
        """Connection refused → status 'down'"""
        
    def test_api_health_returns_yellow_on_slow(self):
        """Response >2s → status 'degraded'"""
        
    def test_db_health_returns_green_on_select(self):
        """SELECT 1 success → status 'up'"""
        
    def test_db_health_returns_red_on_failure(self):
        """DB connection failure → status 'down'"""
        
    def test_health_check_cached_60_seconds(self):
        """Second call within 60s returns cached result"""

class TestStatusBarData:
    def test_last_run_date_from_db(self):
        """Fetches most recent weekly_runs row"""
        
    def test_next_run_calculated_from_settings(self):
        """Next Sunday 18:00 based on WEEKLY_RUN_DAY/HOUR"""
        
    def test_watchlist_count_accurate(self):
        """Count matches actual watchlist table rows"""

class TestStatusBarBehavior:
    def test_api_down_disables_analyze_buttons(self):
        """When API status is 'down', analyze buttons are disabled"""
        
    def test_all_up_enables_all_buttons(self):
        """When all services up, buttons are enabled"""
```

#### Success Criteria
- [ ] Status bar visible on every tab
- [ ] All 3 service indicators show correct state
- [ ] Buttons disabled when backend is down
- [ ] Cached health checks (no per-interaction latency)

---

## 🔀 PARALLEL TASK GROUP: symbol-typeahead

### F7 — Symbol Input: Validation and Typeahead

#### Problem
Symbol input accepts any string with no validation. Typos cause silent failures across the entire app.

#### Technical Design

**Files to create/modify:**
- `src/plutus/dashboard/components.py` — `symbol_input()` reusable component
- `src/plutus/data/universe.py` — Add `search_symbols(query)` function
- All dashboard modules that accept symbol input — replace `st.text_input` with `symbol_input()`

**Implementation Steps:**
1. Load `seed_universe.csv` + user watchlist into a combined symbol list
2. Create `search_symbols(query: str) -> List[SymbolMatch]` function with fuzzy matching
3. Build `symbol_input()` Streamlit component using `st.selectbox` with search
4. Add validation states:
   - ✅ Known symbol (in universe or watchlist)
   - ⚠️ Unknown symbol (yellow warning: "Not in universe. Analysis may fail.")
   - 🚫 Delisted/merged symbol (show correct alternative)
5. Replace all `st.text_input` for symbols across dashboard
6. Store symbols uppercase always

**Symbol Search Logic:**
```python
def search_symbols(query: str) -> List[SymbolMatch]:
    """
    Case-insensitive prefix + substring match against:
    1. seed_universe.csv (symbol + company name)
    2. User watchlist
    Returns top 10 matches sorted by relevance.
    """
```

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f7_symbol_input.py`

```python
class TestSymbolSearch:
    def test_exact_match_returns_first(self):
        """'RELIANCE' returns RELIANCE as first result"""
        
    def test_prefix_match_works(self):
        """'HDFC' returns HDFCBANK, HDFCAMC, HDFCLIFE..."""
        
    def test_case_insensitive(self):
        """'hdfc' matches same as 'HDFC'"""
        
    def test_company_name_match(self):
        """'Infosys' matches INFY symbol"""
        
    def test_empty_query_returns_empty(self):
        """'' returns no results"""
        
    def test_no_match_returns_empty(self):
        """'XYZNOTREAL' returns empty list"""
        
    def test_max_10_results(self):
        """Never returns more than 10 matches"""
        
    def test_watchlist_symbols_included(self):
        """Symbols in watchlist but not universe still match"""

class TestSymbolValidation:
    def test_known_symbol_valid(self):
        """Universe symbol → valid"""
        
    def test_unknown_symbol_warns(self):
        """Non-universe symbol → warning state"""
        
    def test_output_always_uppercase(self):
        """'reliance' → stored as 'RELIANCE'"""
        
    def test_delisted_symbol_shows_alternative(self):
        """'HDFC' → warning with 'use HDFCBANK' suggestion"""
```

#### Success Criteria
- [ ] All symbol inputs use searchable dropdown
- [ ] Typing 3+ chars shows matching suggestions
- [ ] Unknown symbols show warning (not silent fail)
- [ ] Symbols always stored uppercase
- [ ] Works across Strategy Lab, Analyze, Portfolio, Signals tabs

---

## 🔀 PARALLEL TASK GROUP: strategy-lab-empty-state

### F8 — Strategy Lab: Show Bundle Comparison Table on First Load

#### Problem
Strategy Lab shows a blank page when no weekly run data exists. New users see nothing and don't know what to do.

#### Technical Design

**Files to modify:**
- `src/plutus/dashboard/strategy_lab.py` — Add empty state handling

**Implementation Steps:**
1. Check if `weekly_runs` table has any data
2. If empty: show theoretical comparison table with expected bundle characteristics
3. Add clear label: "No backtest data yet. Run a manual backtest below or wait for Sunday pipeline."
4. When data exists: show real comparison table (existing behavior)
5. After F1 fix, manual backtest result shows:
   - Mini equity curve chart
   - Collapsible trade log table
   - Comparison: "How this bundle vs. other 4 on this stock/period"

**Theoretical Data (static):**
| Bundle | Expected Win Rate | Logic | Best Regime |
|--------|------------------|-------|-------------|
| Trend | 45–60% | EMA crossover | Trending |
| Reversal | 40–55% | RSI divergence | Ranging |
| Breakout | 35–55% | Volume escape | Pre-breakout |
| SMC | 40–60% | Order blocks | All |
| Composite | 55–70%* | 3-of-4 agree | Low noise |

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f8_strategy_lab_empty.py`

```python
class TestStrategyLabEmptyState:
    def test_no_data_shows_theoretical_table(self):
        """Empty weekly_runs → theoretical comparison table shown"""
        
    def test_no_data_shows_guidance_message(self):
        """Empty state includes guidance text about running backtest"""
        
    def test_all_5_bundles_in_theoretical_table(self):
        """Trend, Reversal, Breakout, SMC, Composite all present"""
        
    def test_with_data_shows_real_table(self):
        """When weekly_runs exists, real data table shown instead"""

class TestBacktestResultDisplay:
    def test_equity_curve_chart_rendered(self):
        """Successful backtest shows P&L equity curve"""
        
    def test_trade_log_table_collapsible(self):
        """Trade log starts collapsed, expandable on click"""
        
    def test_trade_log_has_required_columns(self):
        """Date, Entry, Exit, P&L, Reason columns present"""
        
    def test_bundle_comparison_bar_shown(self):
        """Shows how selected bundle compares to other 4"""
```

#### Success Criteria
- [ ] New users see meaningful content on first visit
- [ ] Theoretical table clearly labelled as non-live data
- [ ] Real data replaces theoretical when available
- [ ] Backtest results show equity curve + trade log

---

## Phase 2B — Execution Order

```
[Pre-requisite] Phase 2A complete (portfolio creation F3 exists, dashboard modules extracted)
     ↓
[Parallel Group 1] F6 (status bar) + F7 (symbol typeahead) + F8 (strategy lab empty state)
     ↓
[Sequential] F5 (paper trading) — depends on F7 for symbol input component
     ↓
[Sequential] Integration: verify F5 uses F7 typeahead, F6 bar disables F5 when API down
```

**Note:** F5 depends on F7's `symbol_input()` component. Start F7 first or extract the component interface early so F5 can code against it.
