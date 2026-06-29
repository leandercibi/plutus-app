# 07 — Acceptance checklist

This is the gate. Before declaring the v2 work complete, walk through every box. If any item fails, the work is not done — fix it before claiming completion.

The implementer signs off by running the listed commands and pasting the output into the PR description.

## Phase 01 — Repo restructure

- [ ] `pyproject.toml` exists at project root with PEP 621 metadata.
- [ ] `pip install -e .` in a fresh venv succeeds.
- [ ] `python -c "import plutus; print(plutus.__file__)"` resolves to `src/plutus/__init__.py`.
- [ ] `find . -type d -path "*/src/src" 2>/dev/null` returns no results.
- [ ] `find . -type f -name "FINAL_SUMMARY.md" -o -name "TEST_REPORT.md" -o -name "YFINANCE_ISSUES.md" -o -name "dashboard_test.png"` returns no results in tracked files (`git ls-files`).
- [ ] `src/plutus/core/data/ohlcv.py` AngelOne block matches the original byte-for-byte (`diff` returns 0 lines after path normalisation).
- [ ] `git log --oneline | head -3` shows one commit titled `phase 01: ...`.
- [ ] `pytest -q` passes the recorded baseline count (≥ 502 from prior session).

## Phase 02 — Core domain

- [ ] `pytest tests/core/ -q` → 100% of new tests pass.
- [ ] `python -c "from plutus.core import settings, get_params, fetch_ohlcv, run_monitor"` succeeds.
- [ ] `grep -rn "from plutus.swing\|from plutus.accumulation" src/plutus/core/` returns 0 lines.
- [ ] `tests/core/test_alerts_monitor.py` includes the registry pattern test, and the test passes with 2 registered checkers.
- [ ] `tests/core/data/test_regime_subscription.py` confirms BEAR→BULL fires; same-trend writes do not fire.

## Phase 03 — Swing domain

- [ ] `pytest tests/swing/ -q` → all moved tests pass at their new path.
- [ ] `python -c "from plutus.swing import run_weekly_swing, compute_score, check_swing_positions"` succeeds.
- [ ] `python main.py --health-check` exits 0.
- [ ] `grep -rn "from plutus.accumulation" src/plutus/swing/` returns 0 lines.
- [ ] The swing pipeline persists `WeeklyRun` rows identical in shape to before the move (column-by-column diff against a fixture).

## Phase 04 — Accumulation domain

- [ ] `pytest tests/accumulation/ -q` → ≥ 40 tests pass.
- [ ] Migration `012_phase9_accumulation.sql` applies cleanly on fresh and existing DBs.
- [ ] `python -c "from plutus.accumulation import (compute_accumulation_score, AccumScoreBreakdown, AccumClassification, create_position, add_tranche, suggest_trigger_prices, BudgetExceededError, screen_accumulation_universe, run_weekly_accumulation, check_accumulation_positions, on_regime_change)"` succeeds.
- [ ] `python -c "import plutus.accumulation; from plutus.core.alerts.monitor import _REGISTERED_CHECKERS; print([f.__name__ for f in _REGISTERED_CHECKERS])"` outputs a list containing both `check_swing_positions` and `check_accumulation_positions`.
- [ ] Cross-domain import audit:
  - `grep -rn "from plutus.swing" src/plutus/accumulation/` returns exactly **one** line — `from plutus.swing.scoring import smart_money_pillar` inside `accumulation/scoring.py`. No others.
  - `grep -rn "from plutus.accumulation" src/plutus/swing/` returns 0 lines.
- [ ] `accumulation_min_composite`, `t2_drop_pct`, `t3_drop_pct`, `tranches_per_candidate`, `swing_budget_pct`, `accumulation_budget_pct`, `cash_reserve_pct` are all listed in `get_params()` output with the documented defaults.
- [ ] Invariant validator rejects `swing + accum + cash > 100`. Test passes.
- [ ] `settings.ACCUMULATION_ENABLED` defaults to True; setting it to False stops the second pipeline.

## Phase 05 — Dashboard

- [ ] `streamlit run src/plutus/dashboard/app.py` starts cleanly. Sidebar shows: Home, Swing Signals, Swing Positions, Accumulation Candidates, Accumulation Tranches, Settings, Strategy lab.
- [ ] `pytest tests/dashboard/ -q` → ≥ 11 tests pass.
- [ ] Visual smoke test against v2 mockup screenshot:
  - [ ] Sidebar swing items have blue accent when active; accumulation items have purple accent when active.
  - [ ] Regime pill renders in sidebar header.
  - [ ] Home view: 4-card stat row + capital split bar + 2 side-by-side mini-tables.
  - [ ] Accumulation Candidates: score circle (44px) + 3 mini sub-score bars + tranche pip strip + relative strength chip per card.
  - [ ] Accumulation Tranches: pip strip (3 squares) + avg cost + live P&L per row.
  - [ ] Settings: side-by-side cards with capital split bar at the bottom; "exceeds 100%" error shown when input violates the invariant.
- [ ] `grep -rn "compute_accumulation_score\|run_weekly_swing\|run_weekly_accumulation\|create_position\|add_tranche" src/plutus/dashboard/ | grep -v helpers.py | grep -v components/` returns 0 lines (no business logic leaks into view files).

## Phase 06 — Testing

- [ ] `pytest --cov=src/plutus --cov-report=term-missing` shows:
  - `core/data/fundamentals.py` ≥ 95%
  - `accumulation/scoring.py` = 100%
  - `accumulation/tranches.py` ≥ 95%
  - `accumulation/candidates.py` ≥ 85%
  - `accumulation/pipeline.py` ≥ 80%
  - `accumulation/triggers.py` ≥ 90%
- [ ] Integration suite: `pytest -m integration -q` → 3 tests pass.
- [ ] No `@pytest.mark.skip` decorators in the new test files.
- [ ] Domain isolation grep tests (from `06-testing-strategy.md` CI gate) all pass.

## Cross-cutting

- [ ] `python main.py` runs a full weekly cycle end-to-end against a seeded DB with mocked LLM and mocked yfinance — produces 1 `WeeklyRun` row, 1 `AccumulationRun` row, N `Recommendation` rows, M `AccumulationCandidate` rows. No errors in `logs/`.
- [ ] AngelOne rate-limit block (`_ANGEL_RATE_LOCK`, `_ANGEL_MIN_INTERVAL`, `_ANGEL_MINUTE_LIMIT`) is unchanged from baseline (`git diff baseline -- src/plutus/core/data/ohlcv.py` shows only path metadata).
- [ ] `git log --oneline` shows one commit per phase (5–7 commits total). Commit messages are imperative, lowercased, and reference the phase: `phase 04: accumulation scoring module`.
- [ ] README.md has been updated with: install instructions (`pip install -e .`), how to run the dashboard, how to trigger a manual weekly run, and a paragraph each on swing vs accumulation mode.
- [ ] `docs/` contains the migrated `DASHBOARD_USER_GUIDE.md`, `LOCAL_TESTING.md`, `PM_REVIEW.md`. Project root no longer holds them.

## Definition of done

When every box above is ticked AND:

- The user has confirmed the dashboard visually matches the v2 mockup,
- The user has triggered one manual weekly run and seen accumulation candidates appear,
- The user has logged one tranche through the dashboard and seen the position update,

THEN the v2 work is complete. Open a PR titled `v2: dual-domain restructure + accumulation mode` with this checklist pasted into the description, every box ticked and verifiable.

If any box is unticked, do not claim completion. Surface the blocker to the user with what's missing and why.
