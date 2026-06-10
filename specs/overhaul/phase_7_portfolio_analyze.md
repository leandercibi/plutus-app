# Phase 7 — Mock Portfolio + Analyze Card

```yaml
phase_id: phase_7
status: pending
depends_on: [phase_1, phase_4a]
blocks: [phase_8]
estimated_effort: 4 days
test_framework: pytest + streamlit.testing.v1.AppTest
```

## Goal

The user reported:
- "Mock portfolio tab is non-functional — after a trade was mocked, nothing showed in the dashboard."
- "The analyze button returns a whole big JSON that's not readable."

Both issues land here.

**7a (Mock portfolio)**: root-cause the silent write failure, then build a real Portfolio tab with open positions, equity curve, trade history with MFE/MAE (free from Phase 4a), and aggregate P&L stats.

**7b (Analyze card)**: replace the JSON dump with a structured card — recommendation badge, sub-score bar chart, price levels overlaid on candle chart, position-sizing block, risk-flag chips, narrative paragraph (collapsed by default).

## Acceptance criteria

- [ ] Submitting a mock trade from the dashboard form appears in Portfolio tab within 5s
- [ ] Portfolio tab shows: open positions table, equity curve (Plotly), trade history with MFE/MAE, win rate / avg winner / avg loser / expectancy
- [ ] Reset portfolio admin action with confirmation
- [ ] Analyze card renders within 2s of click (PRD F2 success criterion)
- [ ] No raw JSON visible by default; `[show raw]` toggle exists
- [ ] Sub-score bar chart shows all 5 pillars color-coded
- [ ] Trade entry form lives in dashboard (no Telegram-only requirement)

## Prerequisites

- Phase 1 done — sub-scores exist in `Recommendation`
- Phase 4a done — outcomes & MFE/MAE in `trade_outcomes_audit`

## Task list

### TASK-7.1 — Root-cause: mock trade ingestion failure

```yaml
parallelizable: no
parallel_group: null
reason: Debug step before building the UI on top.
estimated_effort: 3h
```

**Test first** (regression):
```python
# tests/test_portfolio/test_mock_trade_ingest.py
def test_mock_trade_persists(db_session, monkeypatch):
    from plutus.portfolio.service import submit_mock_trade
    submit_mock_trade(portfolio_name="myport", symbol="RELIANCE", qty=10,
                      entry_price=1500.0, stop=1470.0, target=1560.0)
    from plutus.db.models import Position
    rows = db_session.query(Position).filter_by(symbol="RELIANCE").all()
    assert len(rows) == 1
    assert rows[0].entry_price == 1500.0

def test_mock_trade_visible_in_portfolio_query(db_session):
    submit_mock_trade(...)
    from plutus.portfolio.service import get_open_positions
    positions = get_open_positions("myport")
    assert len(positions) == 1
```

**Investigation steps**:
1. Examine `src/plutus/db/models.py` — does `Position` table exist and have the right columns?
2. Trace dashboard form submit handler — is it calling the right write path?
3. Check if Telegram bot writes via a different path (`127.0.0.1:8001`) that the dashboard isn't using.

**Files to fix** (TBD — depends on RCA):
- Likely candidates: `src/plutus/dashboard/portfolio.py`, `src/plutus/portfolio/service.py`, `src/plutus/db/models.py`.

**Acceptance**: regression tests green; manual submit visible in DB.

---

### Parallel group 7A — Portfolio tab components (TASK-7.2 through TASK-7.5)

### TASK-7.2 — Open positions table

```yaml
parallelizable: yes
parallel_group: 7A
estimated_effort: 3h
```

**Test first** (Streamlit AppTest):
```python
# tests/dashboard/test_portfolio_open_positions.py
def test_empty_state(db_session):
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    assert any("No open positions" in md.value for md in at.markdown)

def test_open_position_renders(db_session, monkeypatch):
    seed_position(db_session, symbol="RELIANCE", qty=10, entry=1500, stop=1470, target=1560)
    monkeypatch.setattr("plutus.data.ohlcv.fetch_live_price", lambda s, **kw: 1530.0)
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    df = at.dataframe[0].value
    assert "RELIANCE" in df["symbol"].values
    pnl_row = df[df["symbol"] == "RELIANCE"].iloc[0]
    assert pnl_row["P&L₹"] == pytest.approx((1530 - 1500) * 10, rel=0.01)
    assert pnl_row["P&L%"] == pytest.approx(2.0, rel=0.01)
```

**Files to create/modify**:
- `src/plutus/dashboard/portfolio.py` — `render_open_positions(portfolio_name)`.

Columns: `symbol, qty, entry, LTP, P&L₹, P&L%, stop, target, days_held`.

---

### TASK-7.3 — Equity curve (Plotly)

```yaml
parallelizable: yes
parallel_group: 7A
estimated_effort: 3h
```

**Test first**:
```python
def test_equity_curve_renders(db_session):
    seed_trade_history(db_session, [...])
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    # Plotly charts render as st.plotly_chart; AppTest captures via at.plotly_chart
    assert len(at.plotly_chart) >= 1

def test_equity_starts_at_initial_capital(db_session):
    seed_trade_history(db_session, capital=100000, trades=[...])
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    fig_json = at.plotly_chart[0].value.to_dict()
    assert fig_json["data"][0]["y"][0] == 100000
```

**Files to modify**: `src/plutus/dashboard/portfolio.py` — `render_equity_curve(portfolio_name)`.

---

### TASK-7.4 — Trade history table with MFE/MAE

```yaml
parallelizable: yes
parallel_group: 7A
estimated_effort: 2h
```

**Test first**:
```python
def test_history_includes_mfe_mae(db_session):
    seed_closed_trades_with_audit(db_session, [...])
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    # Find the history table
    history_df = next(df.value for df in at.dataframe if "MFE%" in df.value.columns)
    assert "MFE%" in history_df.columns
    assert "MAE%" in history_df.columns
    assert "outcome" in history_df.columns
```

**Files to modify**: `src/plutus/dashboard/portfolio.py` — `render_trade_history(portfolio_name)`.

---

### TASK-7.5 — Aggregate P&L stats

```yaml
parallelizable: yes
parallel_group: 7A
estimated_effort: 2h
```

**Test first**:
```python
def test_metrics_render(db_session):
    seed_closed_trades(db_session, [
        {"pnl_pct": 5.0}, {"pnl_pct": -2.0}, {"pnl_pct": 3.0}, {"pnl_pct": -1.0},
    ])
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Win Rate"] == "50.0%"
    assert "₹" in metrics["Avg Winner"]
    assert "Expectancy" in metrics
```

**Files to modify**: `src/plutus/dashboard/portfolio.py` — `render_portfolio_metrics(portfolio_name)`.

Display via `st.metric()`:
- Win rate (%)
- Average winner (₹)
- Average loser (₹)
- Expectancy = win_rate × avg_winner + (1 - win_rate) × avg_loser
- Open positions count
- Total P&L (₹)

---

### TASK-7.6 — Trade entry form

```yaml
parallelizable: yes
parallel_group: 7B
estimated_effort: 3h
```

**Test first**:
```python
def test_form_submit_creates_position(db_session):
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    at.text_input(key="symbol_input").set_value("RELIANCE")
    at.number_input(key="qty_input").set_value(10)
    at.number_input(key="entry_input").set_value(1500.0)
    at.number_input(key="stop_input").set_value(1470.0)
    at.number_input(key="target_input").set_value(1560.0)
    at.button(key="submit_trade").click()
    at.run()
    from plutus.db.models import Position
    assert db_session.query(Position).filter_by(symbol="RELIANCE").count() == 1

def test_form_validates_rr(db_session):
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    at.text_input(key="symbol_input").set_value("RELIANCE")
    at.number_input(key="entry_input").set_value(1500.0)
    at.number_input(key="stop_input").set_value(1490.0)
    at.number_input(key="target_input").set_value(1510.0)   # R:R = 1.0
    at.button(key="submit_trade").click()
    at.run()
    assert any("R:R" in md.value for md in at.markdown)   # warning shown
    # Should NOT have submitted
    assert db_session.query(Position).count() == 0
```

**Files to modify**: `src/plutus/dashboard/portfolio.py` — `render_trade_entry_form()`.

---

### TASK-7.7 — Reset portfolio admin action

```yaml
parallelizable: yes
parallel_group: 7B
estimated_effort: 1h
```

**Test first**:
```python
def test_reset_requires_confirmation(db_session):
    seed_position(db_session, ...)
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    at.button(key="reset_portfolio_open").click()
    at.run()
    # Confirmation dialog visible
    assert any("Are you sure" in md.value for md in at.markdown)
    # DB unchanged
    assert db_session.query(Position).count() == 1

def test_reset_confirm_clears_positions(db_session):
    seed_position(db_session, ...)
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    at.button(key="reset_portfolio_open").click()
    at.run()
    at.button(key="reset_portfolio_confirm").click()
    at.run()
    assert db_session.query(Position).count() == 0
```

---

### TASK-7.8 — Analyze card: badge + sub-score chart

```yaml
parallelizable: yes
parallel_group: 7C
estimated_effort: 4h
```

**Test first**:
```python
# tests/dashboard/test_analyze_card.py
def test_card_renders_recommendation_badge(mock_analysis_result):
    at = AppTest.from_function(lambda: render_analyze_card(mock_analysis_result))
    at.run()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Recommendation") == "BUY"
    assert metrics.get("Composite Score") == "75"

def test_sub_score_chart_present(mock_analysis_result):
    at = AppTest.from_function(lambda: render_analyze_card(mock_analysis_result))
    at.run()
    # Sub-score chart is a plotly bar chart
    assert any(c.value.layout.title.text == "Sub-Score Breakdown" for c in at.plotly_chart)

def test_no_raw_json_by_default(mock_analysis_result):
    at = AppTest.from_function(lambda: render_analyze_card(mock_analysis_result))
    at.run()
    # Raw JSON is inside an expander; closed by default
    expanders = [e for e in at.expander if "Raw JSON" in e.label]
    assert len(expanders) == 1
    # The expander must NOT be expanded by default
    assert expanders[0].expanded is False
```

**Files to create**:
- `src/plutus/dashboard/analyze_card.py` — `render_analyze_card(result: dict) -> None`.

---

### TASK-7.9 — Analyze card: price levels on chart

```yaml
parallelizable: yes
parallel_group: 7C
estimated_effort: 3h
```

**Test first**:
```python
def test_chart_has_entry_zone_band(mock_analysis_result):
    at = AppTest.from_function(lambda: render_analyze_card(mock_analysis_result))
    at.run()
    fig_json = at.plotly_chart[0].value.to_dict()
    shapes = fig_json["layout"].get("shapes", [])
    assert any(s["type"] == "rect" and "entry" in s.get("name", "").lower() for s in shapes)

def test_chart_has_t1_t2_sl_lines(mock_analysis_result):
    at = AppTest.from_function(lambda: render_analyze_card(mock_analysis_result))
    at.run()
    fig_json = at.plotly_chart[0].value.to_dict()
    shapes = fig_json["layout"].get("shapes", [])
    line_names = {s.get("name", "") for s in shapes if s["type"] == "line"}
    assert "T1" in line_names or any("T1" in n for n in line_names)
    assert any("SL" in n for n in line_names)
```

**Files to modify**: `src/plutus/dashboard/analyze_card.py`.

---

### TASK-7.10 — Analyze card: position sizing + risk chips + narrative

```yaml
parallelizable: yes
parallel_group: 7C
estimated_effort: 2h
```

**Test first**:
```python
def test_position_sizing_block(mock_analysis_result):
    at = AppTest.from_function(lambda: render_analyze_card(mock_analysis_result))
    at.run()
    metrics = {m.label: m.value for m in at.metric}
    assert "Shares" in metrics
    assert "Exposure" in metrics
    assert "Risk" in metrics

def test_risk_chips_render(mock_analysis_result_with_flags):
    at = AppTest.from_function(lambda: render_analyze_card(mock_analysis_result_with_flags))
    at.run()
    chip_texts = [md.value for md in at.markdown if "chip" in md.value.lower()]
    assert any("F&O ban" in c for c in chip_texts)

def test_narrative_collapsed_by_default(mock_analysis_result):
    at = AppTest.from_function(lambda: render_analyze_card(mock_analysis_result))
    at.run()
    narrative_expander = next(e for e in at.expander if "Thesis" in e.label)
    assert narrative_expander.expanded is False
```

---

### TASK-7.11 — Analyze button latency (PRD F2 success criterion)

```yaml
parallelizable: no
parallel_group: null
estimated_effort: 1h
```

**Test first**:
```python
def test_analyze_progress_within_2s(monkeypatch):
    """User must see progress within 2s; final render can take longer."""
    import time
    monkeypatch.setattr("plutus.agents.graph.run_analysis", lambda s: time.sleep(5) or mock_result)
    at = AppTest.from_file("src/plutus/dashboard/analyze_card.py")
    at.run()
    t0 = time.time()
    at.button(key="analyze_RELIANCE").click()
    at.run()
    t1 = time.time()
    # Spinner / progress visible
    assert any("Analysing" in md.value for md in at.markdown) or len(at.spinner) > 0
    assert t1 - t0 < 2.0
```

**Files to modify**: `src/plutus/dashboard/analyze_card.py` — use `st.spinner("Analysing...")` wrapper.

## Streamlit considerations

**Key AppTest patterns used here**:
- `at.dataframe[i].value` — pandas DataFrame
- `at.metric[i].value`, `.label`, `.delta` — string metrics
- `at.plotly_chart[i].value` — Plotly Figure object; access via `.to_dict()`
- `at.expander[i].label`, `.expanded` — boolean
- `at.spinner` — list of active spinners during a run

**Form submission** requires calling `at.run()` after `.click()` to re-render.

**Session state** for portfolio name selection:
```python
at.session_state["active_portfolio"] = "myport"
at.run()
```

## Verification

```bash
pytest tests/test_portfolio/ tests/dashboard/test_portfolio_*.py tests/dashboard/test_analyze_card.py -v
# Manual flow:
#   1. Submit a mock trade via the form
#   2. Confirm row appears in open positions table
#   3. Click Analyze on a fixture symbol; verify card renders in <2s with no raw JSON
```

## Done definition

- [ ] All 11 tasks complete; tests green
- [ ] Manual portfolio flow verified end-to-end
- [ ] Analyze button latency under 2s for the spinner

## References

- Plan: Phase 7 section
- Code anchors:
  - `src/dashboard.py:367–423` — current Signals tab (read-only reference)
  - `src/plutus/db/models.py` — Portfolio, Position
  - `src/plutus/data/ohlcv.py:256` — `fetch_live_price`
  - `src/plutus/weekly/outcomes.py` — audit table for MFE/MAE
- PRD: F2 (analyze card), F3 (portfolio UI) — both subsumed
