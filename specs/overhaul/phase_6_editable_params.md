# Phase 6 — Editable Trading Parameters

```yaml
phase_id: phase_6
status: pending
depends_on: []
blocks: [phase_7]
estimated_effort: 3 days
test_framework: pytest + streamlit.testing.v1.AppTest
```

## Goal

Today, capital and risk caps are baked into the prompt string at `src/plutus/agents/prompts.py:82` (`Capital: ₹1,00,000 INR. Max risk per trade: 5%...`) and `src/plutus/config.py`. The dashboard Settings tab is read-only theatre. After this phase: every trading parameter is editable via Settings UI, persisted to a `trading_params` table, and re-rendered into prompts at agent invocation time. Every weekly_run row stamps a `params_version_id` for reproducibility.

## Acceptance criteria

- [ ] `trading_params` table holds every tunable parameter
- [ ] Settings tab form is editable with inline validation
- [ ] Prompts re-rendered with current params at agent call time (no hardcoded values)
- [ ] `weekly_runs` row stamps `params_version_id` matching the active param row
- [ ] "Re-run weekly with new params" button calls the pipeline endpoint
- [ ] Pillar weights must sum to 100; UI rejects invalid sums
- [ ] Per-portfolio override of `initial_capital` and `max_risk_pct` (used by Phase 7)

## Task list

### TASK-6.1 — Schema: `trading_params`

```yaml
parallelizable: no
estimated_effort: 1h
```

**Test first**:
```python
def test_trading_params_row(db_session):
    from plutus.db.models import TradingParam
    p = TradingParam(param_key="initial_capital", value="100000", value_type="int",
                     min_allowed="10000", max_allowed="10000000",
                     updated_by="leander", updated_at=datetime.utcnow())
    db_session.add(p); db_session.commit()

def test_get_params_returns_typed_dict(db_session):
    seed_default_params(db_session)
    from plutus.config import get_trading_params
    p = get_trading_params()
    assert isinstance(p["initial_capital"], int)
    assert isinstance(p["max_risk_pct_per_trade"], float)
    assert isinstance(p["pillar_weights"], dict)

def test_pillar_weights_sum_to_100():
    from plutus.config import get_trading_params
    p = get_trading_params()
    assert sum(p["pillar_weights"].values()) == 100
```

**Files to modify**:
- `src/plutus/db/models.py` — `TradingParam`.
- `src/plutus/config.py` — `get_trading_params() -> dict`, `set_trading_param(key, value, updated_by)`.
- `migrations/00X_trading_params.sql` — DDL + seed defaults.

**Default values** (seeded by migration):
| param_key | value | type | min | max |
|---|---|---|---|---|
| initial_capital | 100000 | int | 10000 | 10000000 |
| max_risk_pct_per_trade | 5.0 | float | 0.5 | 5.0 |
| min_rr_ratio | 2.0 | float | 1.5 | 4.0 |
| hold_days_min | 3 | int | 1 | 30 |
| hold_days_max | 10 | int | 1 | 30 |
| max_open_positions | 4 | int | 1 | 20 |
| max_pct_capital_per_trade | 30.0 | float | 5.0 | 50.0 |
| buy_threshold | 70 | int | 50 | 95 |
| watch_threshold | 55 | int | 30 | 80 |
| avoid_threshold | 35 | int | 20 | 50 |
| pillar_weight_technical | 40 | int | 10 | 70 |
| pillar_weight_smart_money | 15 | int | 5 | 40 |
| pillar_weight_sentiment | 15 | int | 5 | 40 |
| pillar_weight_regime | 15 | int | 5 | 40 |
| pillar_weight_rr | 15 | int | 5 | 40 |
| auto_tune_enabled | false | bool | — | — |

**Acceptance**: tests green; default seed runs cleanly.

---

### TASK-6.2 — Prompts become template strings

```yaml
parallelizable: no
estimated_effort: 2h
```

**Test first**:
```python
def test_synthesizer_prompt_renders_with_capital(monkeypatch):
    monkeypatch.setattr("plutus.config.get_trading_params",
                        lambda: {"initial_capital": 200000, "max_risk_pct_per_trade": 2.0, ...})
    from plutus.agents.prompts import render_synthesizer_prompt
    p = render_synthesizer_prompt()
    assert "₹2,00,000" in p or "200000" in p
    assert "5%" not in p   # hardcoded value gone
    assert "2%" in p

def test_risk_manager_prompt_uses_min_rr_2():
    monkeypatch.setattr("plutus.config.get_trading_params", lambda: {"min_rr_ratio": 2.0, ...})
    p = render_risk_manager_prompt()
    assert "R:R ratio < 2.0" in p
```

**Files to modify**:
- `src/plutus/agents/prompts.py` — convert `SYNTHESIZER_PROMPT`, `RISK_MANAGER_PROMPT` from constants to `render_*_prompt()` functions using `.format()` or f-strings against `get_trading_params()`.
- Call sites in `synthesizer.py`, `risk_manager.py`, `graph.py` — call the renderer at invocation time, not at module import.

**Acceptance**: prompt strings contain no hardcoded capital/risk values.

---

### TASK-6.3 — Settings UI form

```yaml
parallelizable: yes
parallel_group: 6_UI
estimated_effort: 4h
```

**Test first** (Streamlit AppTest):
```python
# tests/dashboard/test_settings_form.py
from streamlit.testing.v1 import AppTest

def test_form_renders_with_defaults(db_session):
    seed_default_params(db_session)
    at = AppTest.from_file("src/plutus/dashboard/settings_form.py")
    at.run()
    capital_input = at.number_input(key="initial_capital")
    assert capital_input.value == 100000

def test_capital_below_min_shows_error(db_session, monkeypatch):
    seed_default_params(db_session)
    at = AppTest.from_file("src/plutus/dashboard/settings_form.py")
    at.run()
    at.number_input(key="initial_capital").set_value(5000)   # below 10k min
    at.button(key="save_params").click()
    at.run()
    assert any("must be at least" in md.value.lower() for md in at.markdown)

def test_pillar_weights_must_sum_to_100(db_session):
    at = AppTest.from_file("src/plutus/dashboard/settings_form.py")
    at.run()
    at.number_input(key="pillar_weight_technical").set_value(50)
    at.number_input(key="pillar_weight_smart_money").set_value(20)
    # Other pillars stay at 15+15+15 ⇒ total = 115
    at.button(key="save_params").click()
    at.run()
    assert any("must sum to 100" in md.value.lower() for md in at.markdown)

def test_save_updates_db(db_session):
    at = AppTest.from_file("src/plutus/dashboard/settings_form.py")
    at.run()
    at.number_input(key="initial_capital").set_value(250000)
    at.button(key="save_params").click()
    at.run()
    from plutus.config import get_trading_params
    assert get_trading_params()["initial_capital"] == 250000

def test_rerun_pipeline_button_calls_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr("plutus.api.routes.trigger_pipeline_run", lambda: calls.append(1))
    at = AppTest.from_file("src/plutus/dashboard/settings_form.py")
    at.run()
    at.button(key="rerun_pipeline").click()
    at.run()
    assert len(calls) == 1
```

**Files to create**:
- `src/plutus/dashboard/settings_form.py` — Streamlit page (a tab under Settings, alongside Tuning from Phase 4.5).

**Form layout**:
```
[Capital & Risk]
  initial_capital (number_input, min=10k, max=10cr)
  max_risk_pct_per_trade (number_input)
  max_open_positions (number_input)
  max_pct_capital_per_trade (number_input)

[R:R & Hold]
  min_rr_ratio (number_input)
  hold_days_min / hold_days_max (number_inputs)

[Score Thresholds]
  buy_threshold / watch_threshold / avoid_threshold (number_inputs)

[Pillar Weights — must sum to 100]
  5 number_inputs + live sum display

[Self-Tuning]
  auto_tune_enabled (checkbox)

[Save Changes] [Re-run Pipeline with New Params]
```

---

### TASK-6.4 — `params_version_id` stamping

```yaml
parallelizable: yes
parallel_group: 6_UI
estimated_effort: 1h
```

**Test first**:
```python
def test_weekly_run_stamps_params_version(db_session, monkeypatch):
    set_trading_param("initial_capital", 200000, "leander")
    weekly_pipeline()
    run = db_session.query(WeeklyRun).order_by(WeeklyRun.id.desc()).first()
    assert run.params_version_id is not None
    # Stamp matches the most recent params updated_at
    latest_param = db_session.query(TradingParam).order_by(TradingParam.updated_at.desc()).first()
    assert run.params_version_id == latest_param.updated_at.isoformat()
```

**Files to modify**:
- `src/plutus/db/models.py` — add `params_version_id` column to `WeeklyRun`.
- `main.py` (weekly_pipeline) — capture version at start.

---

### TASK-6.5 — Per-portfolio override (forward declare for Phase 7)

```yaml
parallelizable: yes
parallel_group: 6_UI
estimated_effort: 1h
```

**Test first**:
```python
def test_portfolio_can_override_capital(db_session):
    from plutus.db.models import Portfolio
    p = Portfolio(name="myport", capital_override=50000, max_risk_pct_override=2.0)
    db_session.add(p); db_session.commit()

    from plutus.config import get_trading_params_for_portfolio
    params = get_trading_params_for_portfolio("myport")
    assert params["initial_capital"] == 50000
    assert params["max_risk_pct_per_trade"] == 2.0
```

**Files to modify**:
- `src/plutus/db/models.py` — add `capital_override`, `max_risk_pct_override` to `Portfolio` (nullable).
- `src/plutus/config.py` — `get_trading_params_for_portfolio(name)`.

## Streamlit considerations

- Uses `st.tabs(["General", "Risk", "Score", "Self-Tune"])` to organise the form.
- Save persists immediately on button click; no in-memory drift.
- `at.number_input(key="...")` — set with `.set_value(n)`, then `at.run()` to re-render.

## Verification

```bash
pytest tests/test_config/ tests/dashboard/test_settings_form.py -v
# Manual: open dashboard, edit max_risk from 5 to 2, save, re-run pipeline,
# inspect any new recommendation's max_loss_inr <= 2000
```

## Done definition

- [ ] All 5 tasks complete; tests green
- [ ] No hardcoded capital/risk values remain in prompts.py
- [ ] Manual flow verified end-to-end

## References

- Plan: Phase 6 section
- Code anchors:
  - `src/plutus/agents/prompts.py:82` — RISK_MANAGER_PROMPT hardcoded values
  - `src/plutus/agents/prompts.py:110` — SYNTHESIZER_PROMPT hardcoded values
  - `src/plutus/config.py` — current static settings
  - `src/plutus/db/models.py` — WeeklyRun, Portfolio
