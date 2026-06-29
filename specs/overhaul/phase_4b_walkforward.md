# Phase 4b — Walk-Forward Harness

```yaml
phase_id: phase_4b
status: pending
depends_on: [phase_0, phase_4a]
blocks: []
estimated_effort: 3 days
test_framework: pytest
```

## Goal

Today's backtest reports IS (in-sample) Sharpe only. Strategies that overfit the 90-day window look great IS and bomb OOS. Walk-forward splits the data into rolling train/validate/test windows; running each bundle through this harness flags overfit candidates (OOS Sharpe drops > 50% from IS) before they reach the recommendation engine.

## Acceptance criteria

- [ ] `walk_forward(symbol, bundle, window=30, step=7)` returns `WalkForwardReport` with per-window IS/OOS Sharpe
- [ ] CLI: `python -m plutus.backtesting.walk_forward --symbol RELIANCE --bundle trend --window 30 --step 7`
- [ ] Results persisted to `walk_forward_runs` table
- [ ] Overfit flag set when `(IS_sharpe - OOS_sharpe) / IS_sharpe > 0.5` for ≥ 50% of windows
- [ ] Strategy Lab UI surfaces the report (button under "Run Walk-Forward")

## Task list

### TASK-4b.1 — Schema: `walk_forward_runs` table

```yaml
parallelizable: no
estimated_effort: 30min
```

**Test first**:
```python
def test_walk_forward_run_row(db_session):
    from plutus.db.models import WalkForwardRun
    row = WalkForwardRun(symbol="RELIANCE", bundle="trend", window_days=30, step_days=7,
                         is_sharpe_median=1.8, oos_sharpe_median=0.7, overfit_flag=True,
                         windows_json=[{...}])
    db_session.add(row); db_session.commit()
```

**Files**: `src/plutus/db/models.py` + migration.

---

### TASK-4b.2 — IS/OOS split logic

```yaml
parallelizable: no
estimated_effort: 4h
```

**Test first**:
```python
# tests/test_walk_forward/test_split.py
def test_window_split_count():
    """90 days, window=30, step=7 ⇒ ((90-30)/7) ≈ 8 walks."""
    bars = make_bars(90)
    windows = list(split_walk_forward(bars, window_days=30, step_days=7))
    assert 7 <= len(windows) <= 9

def test_each_window_has_is_and_oos():
    """First 21 days IS (70%), next 9 days OOS (30%)."""
    bars = make_bars(90)
    w = next(split_walk_forward(bars, window_days=30, step_days=7))
    assert len(w["is_bars"]) == pytest.approx(21, abs=2)
    assert len(w["oos_bars"]) == pytest.approx(9, abs=2)

def test_no_lookahead_leak():
    """IS bars must have earlier dates than OOS bars."""
    bars = make_bars(90)
    for w in split_walk_forward(bars, window_days=30, step_days=7):
        assert w["is_bars"].index.max() < w["oos_bars"].index.min()
```

**Files**: new `src/plutus/backtesting/walk_forward.py` — `split_walk_forward()`.

---

### TASK-4b.3 — Per-window backtest runner

```yaml
parallelizable: no
estimated_effort: 3h
```

**Test first**:
```python
def test_runs_bundle_on_each_window(monkeypatch):
    monkeypatch.setattr("plutus.backtesting.runner.run_bundle", mock_run_bundle)
    report = walk_forward("RELIANCE", "trend", window_days=30, step_days=7)
    assert len(report.windows) >= 7
    for w in report.windows:
        assert "is_sharpe" in w
        assert "oos_sharpe" in w

def test_overfit_flag_set_when_oos_drops(monkeypatch):
    # Mock IS sharpe high, OOS sharpe low
    ...
    report = walk_forward("RELIANCE", "trend", ...)
    assert report.overfit_flag is True
```

**Files**: extend `walk_forward.py`.

---

### TASK-4b.4 — CLI

```yaml
parallelizable: yes
parallel_group: 4B_post
estimated_effort: 1h
```

**Test first**:
```python
def test_cli_smoke():
    from click.testing import CliRunner
    from plutus.backtesting.walk_forward import cli
    r = CliRunner().invoke(cli, ["--symbol", "RELIANCE", "--bundle", "trend",
                                  "--window", "30", "--step", "7"])
    assert r.exit_code == 0
    assert "IS Sharpe median" in r.output
```

**Files**: add `cli()` to `walk_forward.py`, register entry point.

---

### TASK-4b.5 — Strategy Lab "Run Walk-Forward" button

```yaml
parallelizable: yes
parallel_group: 4B_post
estimated_effort: 2h
```

**Test first** (Streamlit AppTest):
```python
# tests/dashboard/test_strategy_lab_walkforward.py
from streamlit.testing.v1 import AppTest

def test_walkforward_button_renders():
    at = AppTest.from_file("src/plutus/dashboard/strategy_lab.py")
    at.run()
    # Find the button by label
    buttons = [b for b in at.button if "Walk-Forward" in b.label]
    assert len(buttons) == 1

def test_walkforward_button_click_shows_progress(monkeypatch):
    monkeypatch.setattr("plutus.backtesting.walk_forward.walk_forward", lambda *a, **kw: mock_report)
    at = AppTest.from_file("src/plutus/dashboard/strategy_lab.py")
    at.session_state["wf_symbol"] = "RELIANCE"
    at.session_state["wf_bundle"] = "trend"
    at.run()
    at.button(key="run_walkforward").click()
    at.run()
    # Result table renders
    assert any("OOS Sharpe" in df.columns.tolist() for df in at.dataframe)
```

**Files to modify**: `src/plutus/dashboard/strategy_lab.py` — add button + result rendering.

## Streamlit considerations

Use `streamlit.testing.v1.AppTest` for all dashboard tests. Common pattern:

```python
at = AppTest.from_file("src/plutus/dashboard/strategy_lab.py", default_timeout=20)
at.session_state["foo"] = "bar"
at.run()
at.button(key="run_walkforward").click()
at.run()
assert at.dataframe[0].value.shape[0] == 8   # 8 windows
```

Key AppTest accessors:
- `at.button[i]` / `at.button(key="k")` — interactive
- `at.text_input[i]` — interactive
- `at.dataframe[i].value` — pandas df
- `at.metric[i].value` — string
- `at.session_state["k"]` — read/write

## Verification

```bash
pytest tests/test_walk_forward/ tests/dashboard/test_strategy_lab_walkforward.py -v
python -m plutus.backtesting.walk_forward --symbol RELIANCE --bundle trend --window 30 --step 7
```

## Done definition

- [ ] All 5 tasks complete; tests green
- [ ] CLI on RELIANCE Trend produces ≥ 7 windows of IS/OOS pairs
- [ ] Strategy Lab button visible and functional

## References

- Plan: Phase 4b section
- Code anchors:
  - `src/plutus/backtesting/runner.py:60` — `run_bundle` consumed per window
  - `src/plutus/dashboard/strategy_lab.py` — UI surface
