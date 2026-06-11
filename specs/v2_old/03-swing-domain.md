# 03 — Swing domain

## Goal

Consolidate the swing trading code under `src/plutus/swing/` so it is a self-contained domain with one public entry point per use case. No new business logic. This phase is the "move-and-cement" step before accumulation is added alongside.

## Scope summary

The swing domain owns:

- The deterministic scoring rubric (`swing/scoring.py` — already done in Phase 1 of the old overhaul).
- The 7 strategy bundles (`swing/strategies/` — Trend, Reversal, Breakout, SMC, Composite, VCP, PEAD).
- The backtesting harness (`swing/backtesting/` — runner, paper trader, walk-forward).
- The 6 LLM agent nodes (`swing/agents/` — technical, sentiment, smart_money, risk_manager, synthesizer, graph).
- The weekly swing pipeline (`swing/pipeline.py` — runs Sun 18:00 IST).
- The outcome tracker and postmortem (`swing/outcomes.py`, `swing/postmortem.py`).
- The position-aware alerts (`swing/triggers.py`).

## Tasks

### 03.1 — Pin the swing public surface

`src/plutus/swing/__init__.py`:

```python
from plutus.swing.scoring import (
    compute_score,
    ScoreBreakdown,
    Classification,
    PILLAR_WEIGHTS,
    BUY_THRESHOLD,
    WATCH_THRESHOLD,
    HOLD_THRESHOLD,
)
from plutus.swing.pipeline import run_weekly_swing
from plutus.swing.outcomes import track_outcomes
from plutus.swing.triggers import check_swing_positions

import plutus.swing.triggers  # noqa: F401  (registers checker on import)
```

The `import plutus.swing.triggers` line registers `check_swing_positions` with `core.alerts.monitor` via the `register_position_checker` call.

Test:

```python
# tests/swing/test_public_surface.py
def test_swing_public_surface():
    from plutus import swing
    for name in [
        "compute_score", "ScoreBreakdown", "Classification",
        "PILLAR_WEIGHTS", "BUY_THRESHOLD", "WATCH_THRESHOLD", "HOLD_THRESHOLD",
        "run_weekly_swing", "track_outcomes", "check_swing_positions",
    ]:
        assert hasattr(swing, name)

def test_importing_swing_registers_position_checker():
    from plutus.core.alerts.monitor import _REGISTERED_CHECKERS
    _REGISTERED_CHECKERS.clear()
    import importlib
    import plutus.swing
    importlib.reload(plutus.swing)
    fn_names = [fn.__name__ for fn in _REGISTERED_CHECKERS]
    assert "check_swing_positions" in fn_names
```

Acceptance: both tests pass.

### 03.2 — Extract `run_weekly_swing` from `main.py`

The current `main.py` `weekly_pipeline()` mixes swing run + (future) accumulation run + scheduling. Split:

`swing/pipeline.py`:

```python
async def run_weekly_swing(
    db_session,
    run_date: date,
    *,
    universe: list[str] | None = None,
    top_n: int = 20,
) -> WeeklyRun:
    """Execute the full swing pipeline:
        1. Load universe (default: get_universe('swing'))
        2. Score each candidate via backtests
        3. Run agent graph on top_n
        4. Persist WeeklyRun + Recommendation rows
        5. Return the saved WeeklyRun
    """
```

The function body is the current swing block. The only behaviour change is parameterising `universe` and `top_n` (defaults preserve current behaviour).

Test (integration, fake LLM):

```python
# tests/swing/test_pipeline.py
@pytest.mark.asyncio
async def test_run_weekly_swing_persists_weekly_run(in_memory_db, fake_llm, seeded_universe):
    run = await run_weekly_swing(in_memory_db, run_date=date(2026, 6, 7))
    assert run.id is not None
    assert run.stocks_screened > 0
    assert run.stocks_analysed == 20  # default top_n
    recs = in_memory_db.query(Recommendation).filter_by(weekly_run_id=run.id).all()
    assert len(recs) == run.stocks_analysed

@pytest.mark.asyncio
async def test_run_weekly_swing_respects_top_n(in_memory_db, fake_llm, seeded_universe):
    run = await run_weekly_swing(in_memory_db, run_date=date(2026, 6, 7), top_n=5)
    assert run.stocks_analysed == 5
```

The `fake_llm` fixture stubs `openrouter_client.call_llm` to return a deterministic JSON blob. See `06-testing-strategy.md` for the fixture spec.

Acceptance: both tests pass.

### 03.3 — Extract `check_swing_positions` into `swing/triggers.py`

Move from `core/alerts/monitor.py` (legacy `check_open_positions`) the swing-position checks:

```python
# swing/triggers.py
from plutus.core.alerts.monitor import register_position_checker
from plutus.core.db.models import (
    AlertType, PaperTrade, TradeStatus, Recommendation,
)

def check_swing_positions(db, channels) -> int:
    """Iterate open PaperTrade rows; fire alerts on PRE_SL, T1, T2, trend invalidation."""
    fired = 0
    for trade in db.query(PaperTrade).filter_by(status=TradeStatus.OPEN).all():
        fired += _check_one_swing_position(db, trade, channels)
    return fired

# private helpers preserved from old monitor.py:
#   _check_one_swing_position, _already_sent, _fire_alert

register_position_checker(check_swing_positions)
```

Test:

```python
# tests/swing/test_triggers.py
def test_pre_sl_warning_fires_when_ltp_within_1pct(in_memory_db, monkeypatch, fake_channel):
    trade = _seed_open_trade(in_memory_db, entry=1000, sl=950)
    monkeypatch.setattr("plutus.swing.triggers.fetch_live_price", lambda s: 955)
    fired = check_swing_positions(in_memory_db, [fake_channel])
    assert fired == 1
    assert fake_channel.sent[0].startswith("⚠️ SELL ALERT")

def test_pre_sl_dedup_within_cooldown(in_memory_db, monkeypatch, fake_channel):
    trade = _seed_open_trade(in_memory_db, entry=1000, sl=950)
    monkeypatch.setattr("plutus.swing.triggers.fetch_live_price", lambda s: 955)
    check_swing_positions(in_memory_db, [fake_channel])
    fired = check_swing_positions(in_memory_db, [fake_channel])  # within 1h
    assert fired == 0
    assert len(fake_channel.sent) == 1

def test_target1_hit_fires_once(...):
    ...
def test_target2_hit_fires_once(...):
    ...
def test_trend_invalidated_after_5_days_below_ema20(...):
    ...
```

Acceptance: 5 tests pass. All pre-existing `tests/test_phase8a_alerts.py` tests still pass (rename/move them to `tests/swing/test_triggers.py` as part of this phase if not already done).

### 03.4 — Inventory existing tests, move into `tests/swing/`

Existing test files relevant to swing:

```
tests/test_phase2_f1_backtest.py        → tests/swing/test_backtesting/test_f1_data_validation.py
tests/test_strategies.py                → tests/swing/test_strategies/test_bundles.py
tests/test_backtesting.py               → tests/swing/test_backtesting/test_runner.py
tests/test_scoring/                     → tests/swing/test_scoring/
tests/test_bundle_hardening/            → tests/swing/test_strategies/test_hardening/
tests/test_walk_forward/                → tests/swing/test_backtesting/test_walk_forward/
tests/test_outcomes/                    → tests/swing/test_outcomes/
tests/test_self_finetuning/             → tests/swing/test_postmortem/
tests/test_phase7_portfolio_analyze.py  → tests/swing/test_portfolio.py
tests/test_phase8a_alerts.py            → tests/swing/test_triggers.py
```

Use `git mv` so blame/history survives. Update imports in each file to point at the new module locations (`plutus.swing.scoring`, `plutus.swing.strategies.bundle_trend`, etc.).

Acceptance: `pytest tests/swing/ -q` matches the count of all moved files before the move. `pytest -q` total count is unchanged from phase 02.

## Verification gate for phase 03

- [ ] `tests/swing/test_public_surface.py` passes (2 tests).
- [ ] `tests/swing/test_pipeline.py` passes (2 tests).
- [ ] `tests/swing/test_triggers.py` passes (5 tests).
- [ ] All moved test files run from their new paths with passing counts matching pre-move.
- [ ] `python main.py --health-check` succeeds.
- [ ] `python -c "from plutus.swing import run_weekly_swing, compute_score, check_swing_positions"` succeeds.
- [ ] Domain isolation: `grep -rn "from plutus.accumulation" src/plutus/swing/` returns 0 lines (accumulation does not yet exist; this guards against future leak).

Do not start phase 04 until every box is checked.
