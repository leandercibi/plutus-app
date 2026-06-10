# Phase 2D — Trader Power Features

**Priority:** P2  
**Duration:** 10–14 days  
**Dependency:** Phase 2C complete (F9 signals deep dive exists for drill-down integration)  
**Features:** F12, F13, F14, F15

---

## 🔀 PARALLEL TASK GROUP: score-drilldown

### F12 — Confidence Score Drill-Down

#### Problem
A stock's overall confidence score (e.g., 7.8/10) is opaque. Traders cannot see why a signal was generated or judge which sub-signals to trust.

#### Technical Design

**Files to modify:**
- `src/plutus/dashboard/signals.py` — Add drill-down to F9 deep-dive panel
- `src/plutus/dashboard/components.py` — `render_score_breakdown()` component

**Implementation Steps:**
1. Read sub-scores from `recommendations` table: `technical_score`, `sentiment_score`, `smart_money_score`
2. Read reasoning snippets per sub-score (already stored in recommendation JSON)
3. Render as expandable tree on hover/click:
   ```
   Overall: 7.8 / 10
   ├─ Technical:    8.0   "EMA crossover, Volume breakout, RSI 64"
   ├─ Sentiment:    6.0   "Positive (+3/5): EV push coverage"
   └─ Smart Money:  7.5   "4 MFs accumulating, FII net buyer ₹340Cr"
   ```
4. Visual: color-coded bars per sub-score (green >7, yellow 5-7, red <5)
5. Integrate into F9's expanded signal panel (replaces plain sub-score numbers)

**Data Source:**
```sql
SELECT technical_score, sentiment_score, smart_money_score,
       technical_reasoning, sentiment_reasoning, smart_money_reasoning
FROM recommendations
WHERE symbol = ? AND run_id = ?
```

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f12_score_drilldown.py`

```python
class TestScoreBreakdown:
    def test_renders_overall_score(self):
        """Overall score displayed as X/10"""
        
    def test_renders_three_subscores(self):
        """Technical, Sentiment, Smart Money all shown"""
        
    def test_subscores_have_reasoning_text(self):
        """Each sub-score shows its reasoning snippet"""
        
    def test_color_coding_green_above_7(self):
        """Score > 7 rendered with green indicator"""
        
    def test_color_coding_yellow_5_to_7(self):
        """Score 5-7 rendered with yellow indicator"""
        
    def test_color_coding_red_below_5(self):
        """Score < 5 rendered with red indicator"""
        
    def test_missing_subscore_shows_na(self):
        """If a sub-score is NULL, shows 'N/A' gracefully"""

class TestScoreIntegration:
    def test_drilldown_appears_in_signal_expansion(self):
        """Score breakdown visible in F9 expanded panel"""
        
    def test_drilldown_expandable_from_table_score(self):
        """Clicking score in signals table expands breakdown"""
```

#### Success Criteria
- [ ] All 3 sub-scores visible with reasoning
- [ ] Color-coded for quick scanning
- [ ] Integrated into F9 signal expansion panel
- [ ] Graceful handling of missing/NULL sub-scores

---

## 🔀 PARALLEL TASK GROUP: market-regime

### F13 — Market Regime Badge

#### Problem
Traders have no context about the overall market condition. Strategy selection depends on regime (trending vs. ranging) but this info isn't surfaced.

#### Technical Design

**Files to create/modify:**
- `src/plutus/dashboard/components.py` — `render_market_regime_badge()` component
- `src/plutus/data/ohlcv.py` — Add `get_nifty_regime()` function
- `src/plutus/dashboard/__init__.py` — Render badge on every tab (alongside F6 status bar)

**Implementation Steps:**
1. Fetch Nifty50 (`^NSEI`) OHLCV data (last 60 days) via existing `fetch_ohlcv()`
2. Calculate EMA50 of Nifty50 close prices
3. Determine regime:
   - **BULLISH TRENDING** (📈 green): Close > EMA50 AND EMA50 slope positive
   - **SIDEWAYS** (📊 yellow): Close within ±2% of EMA50
   - **BEARISH TRENDING** (📉 red): Close < EMA50 AND EMA50 slope negative
4. Display as persistent badge (next to or below F6 status bar)
5. Add tooltip: "Market regime affects strategy selection. In BULLISH, Trend and Breakout bundles are prioritised."
6. Cache result for 1 hour (regime doesn't change intraday for swing trading)

**Regime Calculation:**
```python
def get_nifty_regime() -> MarketRegime:
    df = fetch_ohlcv("^NSEI", days=60)
    ema50 = df["close"].ewm(span=50).mean()
    last_close = df["close"].iloc[-1]
    last_ema = ema50.iloc[-1]
    pct_diff = (last_close - last_ema) / last_ema * 100
    
    if pct_diff > 2:
        return MarketRegime.BULLISH
    elif pct_diff < -2:
        return MarketRegime.BEARISH
    else:
        return MarketRegime.SIDEWAYS
```

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f13_market_regime.py`

```python
class TestRegimeCalculation:
    def test_bullish_when_above_ema50_by_2pct(self):
        """Close > EMA50 + 2% → BULLISH"""
        
    def test_bearish_when_below_ema50_by_2pct(self):
        """Close < EMA50 - 2% → BEARISH"""
        
    def test_sideways_when_within_2pct(self):
        """Close within ±2% of EMA50 → SIDEWAYS"""
        
    def test_handles_insufficient_data(self):
        """< 50 bars → returns UNKNOWN regime"""
        
    def test_handles_yfinance_failure(self):
        """yfinance blocked → returns UNKNOWN (no crash)"""
        
    def test_result_cached_1_hour(self):
        """Second call within 1h returns cached regime"""

class TestRegimeBadge:
    def test_bullish_shows_green_badge(self):
        """BULLISH → 📈 green badge"""
        
    def test_bearish_shows_red_badge(self):
        """BEARISH → 📉 red badge"""
        
    def test_sideways_shows_yellow_badge(self):
        """SIDEWAYS → 📊 yellow badge"""
        
    def test_badge_visible_on_all_tabs(self):
        """Badge renders on every tab of dashboard"""
        
    def test_tooltip_present(self):
        """Hovering badge shows strategy context tooltip"""
```

#### Success Criteria
- [ ] Regime badge visible on every tab
- [ ] Correct calculation from Nifty50 EMA50
- [ ] Graceful fallback when yfinance is blocked (UNKNOWN, not crash)
- [ ] Tooltip explains regime → strategy relationship
- [ ] Cached (no per-page-load yfinance call)

---

## 🔀 PARALLEL TASK GROUP: history-outcomes

### F14 — Weekly History: Outcome Tracking Display

#### Problem
History tab shows weekly runs but outcomes (HIT_T1, STOPPED, EXPIRED) are plain text. No visual meaning, no aggregate stats, no performance accountability.

#### Technical Design

**Files to create/modify:**
- `src/plutus/dashboard/history.py` — Outcome badges, hit rate gauge, P&L chart
- `src/plutus/dashboard/components.py` — `render_outcome_badge()`, `render_hit_rate_gauge()`

**Implementation Steps:**
1. Color-code outcome badges:
   - HIT_T1 / HIT_T2: 🟢 green
   - STOPPED: 🔴 red
   - EXPIRED: ⚪ grey
   - PENDING: 🟡 yellow
2. Add hit rate gauge per weekly run: "4 of 7 closed trades hit T1 — 57% win rate"
3. Add P&L attribution chart: stacked bar per stock showing positive/negative contribution
4. Add best/worst trade highlight per week:
   - "Best: TATAMOTORS +6.9% in 4d | Worst: SUNPHARMA -4.8% (stopped)"
5. Summary stats at top: total trades, overall win rate, average R:R achieved

**Data Source:**
```sql
SELECT symbol, outcome, entry_price, exit_price, pnl_pct, hold_days
FROM recommendations
WHERE run_id = ? AND outcome IS NOT NULL
ORDER BY pnl_pct DESC
```

**P&L Chart Spec:**
- Library: Plotly horizontal bar chart
- Green bars: profitable trades (sorted by P&L)
- Red bars: loss trades
- X-axis: P&L %
- Y-axis: Symbol names

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f14_history_outcomes.py`

```python
class TestOutcomeBadges:
    def test_hit_t1_green(self):
        """HIT_T1 outcome → green badge"""
        
    def test_hit_t2_green(self):
        """HIT_T2 outcome → green badge"""
        
    def test_stopped_red(self):
        """STOPPED outcome → red badge"""
        
    def test_expired_grey(self):
        """EXPIRED outcome → grey badge"""
        
    def test_pending_yellow(self):
        """PENDING outcome → yellow badge"""
        
    def test_unknown_outcome_handled(self):
        """NULL or unknown outcome → grey with '?'"""

class TestHitRateGauge:
    def test_calculates_win_rate_correctly(self):
        """4 hits / 7 closed = 57.1%"""
        
    def test_zero_closed_shows_no_data(self):
        """0 closed trades → 'No closed trades yet'"""
        
    def test_all_pending_shows_awaiting(self):
        """All PENDING → 'Awaiting outcomes'"""
        
    def test_includes_trade_count(self):
        """Shows '4 of 7' format"""

class TestPnLChart:
    def test_chart_has_positive_and_negative_bars(self):
        """Mix of winners and losers rendered"""
        
    def test_chart_sorted_by_pnl(self):
        """Best trade at top, worst at bottom"""
        
    def test_chart_labels_include_symbol(self):
        """Each bar labelled with stock symbol"""
        
    def test_empty_week_shows_no_chart(self):
        """No closed trades → chart not rendered"""

class TestBestWorstHighlight:
    def test_best_trade_shown(self):
        """Highest P&L trade highlighted with details"""
        
    def test_worst_trade_shown(self):
        """Lowest P&L trade highlighted with details"""
        
    def test_single_trade_is_both_best_and_worst(self):
        """Only 1 trade → shown as both (or just 'Only trade')"""
```

#### Success Criteria
- [ ] Outcome badges color-coded correctly
- [ ] Hit rate gauge shows per-week win rate
- [ ] P&L chart shows stock-level attribution
- [ ] Best/worst trade highlighted per week
- [ ] Graceful handling of weeks with no closed trades

---

## 🔀 PARALLEL TASK GROUP: export-csv

### F15 — Export: Signals to CSV

#### Problem
No way to share signal shortlist outside the dashboard. Users need to screenshot or manually copy data.

#### Technical Design

**Files to modify:**
- `src/plutus/dashboard/signals.py` — Add export button

**Implementation Steps:**
1. Add "📥 Export to CSV" button above the signals table
2. On click: generate CSV from current recommendation data
3. CSV columns: Symbol, Signal, Score, Entry Low, Entry Mid, Entry High, T1, T2, Stop Loss, R:R, Hold Days, Strategy, Reasoning
4. Use `st.download_button()` for native Streamlit file download
5. Filename: `plutus_signals_{date}.csv`

**CSV Format:**
```csv
Symbol,Signal,Score,Entry_Low,Entry_Mid,Entry_High,T1,T2,Stop_Loss,RR,Hold_Days,Strategy,Reasoning
RELIANCE,BUY,8.1,2375,2385,2395,2480,2560,2320,1.9,7,Trend+Breakout,"EMA crossover with volume..."
HDFCBANK,WATCH,6.2,1680,1690,1700,1750,1800,1640,1.5,5,Composite,"Mixed signals..."
```

#### Test Plan (TDD — Write First)

**Test File:** `tests/test_phase2_f15_export.py`

```python
class TestCSVExport:
    def test_csv_has_correct_headers(self):
        """First row matches expected column names"""
        
    def test_csv_includes_all_signals(self):
        """Row count matches current recommendation count"""
        
    def test_csv_fields_populated(self):
        """No empty required fields in output"""
        
    def test_reasoning_properly_escaped(self):
        """Reasoning with commas/quotes doesn't break CSV"""
        
    def test_filename_includes_date(self):
        """File named plutus_signals_YYYY-MM-DD.csv"""
        
    def test_empty_signals_shows_message(self):
        """No signals → button disabled or message shown"""
        
    def test_download_button_present(self):
        """Export button visible on Signals tab"""

class TestCSVContent:
    def test_score_is_numeric(self):
        """Score column contains float values"""
        
    def test_prices_are_numeric(self):
        """All price columns are numeric (no ₹ symbol)"""
        
    def test_signal_is_valid_enum(self):
        """Signal column is BUY/WATCH/AVOID only"""
```

#### Success Criteria
- [ ] CSV downloads with one click
- [ ] All 13 columns present and populated
- [ ] Special characters in reasoning properly escaped
- [ ] Filename includes current date
- [ ] Works when no signals exist (graceful empty state)

---

## Phase 2D — Execution Order

```
[Pre-requisite] Phase 2C complete (F9 signals expansion exists)
     ↓
[Parallel] F12 (score drill-down) + F13 (market regime) + F14 (history outcomes) + F15 (export CSV)
     ↓
[Sequential] Integration: F12 integrates into F9 panel, F13 badge alongside F6 status bar
```

**Parallel Safety:**
- F12 modifies `signals.py` (adds to F9 panel) — owns the sub-score section
- F13 modifies `components.py` (new badge) + `__init__.py` (render call) — no conflict with F12
- F14 owns `history.py` exclusively — no conflict
- F15 modifies `signals.py` (adds export button above table) — potential conflict with F12

**Conflict Resolution for F12 + F15:**
- F12 adds content inside the expanded row (below table)
- F15 adds a button above the table
- These are different locations in `signals.py` — safe if both workers declare their regions:
  - F15 region: top of `render_signals_tab()` (before table)
  - F12 region: inside `render_deep_dive_panel()` (within expanded row)

---

## Phase 2D — Integration Verification

After all 4 features are complete, verify:

| Check | Expected |
|-------|----------|
| F12 score breakdown inside F9 expanded panel | Sub-scores replace plain numbers |
| F13 badge renders alongside F6 status bar | Both bars visible, no overlap |
| F14 history tab shows colored badges | All outcome types colored correctly |
| F15 export includes F12 sub-scores if present | Optional: sub-scores as extra columns |
| F13 regime + F9 signals | Tooltip mentions which bundles are prioritised for current regime |
