# Shrinkage + Pooled Stats + Walk-Forward + Per-Regime Store — Implementation Report

Branch: `v2-rebuild` · All tests run with `.venv/bin/python`.

## Result

`.venv/bin/python -m pytest tests/backtesting/ -q` → **21 passed in 0.13s**
`ruff check` (all new files) → **All checks passed**
`mypy` (all 4 src modules) → **Success: no issues found in 4 source files**

## Files implemented (TDD: test written + failing first, then impl)

| Module | Source | Test |
|---|---|---|
| Shrinkage | `src/plutus/backtesting/shrinkage.py` | `tests/backtesting/test_shrinkage.py` (4) |
| Walk-forward | `src/plutus/backtesting/walk_forward.py` | `tests/backtesting/test_walk_forward_windows.py` (5) |
| Pooled stats | `src/plutus/backtesting/pooled.py` | `tests/backtesting/test_pooled_min_n_floor.py` (4), `test_pooled_no_per_symbol_sharpe.py` (2) |
| Per-regime store | `src/plutus/backtesting/per_regime.py` | `tests/backtesting/test_per_regime_store.py` (6) |

Also added `tests/backtesting/conftest.py` (in-memory SQLite `session` fixture, mirrors `tests/db/conftest.py` with the FK pragma).

## Key decisions

1. **`shrunk_sharpe`** — exact James-Stein formula from spec §5. `n=0` → returns prior_mean (shrinkage 1.0); verified by `test_formula_exact` and `test_zero_trades_returns_prior_mean`.

2. **`WalkForward`** — `Window` frozen dataclass (start, end). `windows()` tiles train→OOS sliding by `step_days`, stopping when `oos_end > end` so no partial OOS window is yielded. `stats()` filters trades by `entry_date ∈ [window.start, window.end)` and delegates to `stats_from_trades`.

3. **`PooledStats`** — `compute(trades, group_by)` groups ONLY by `bundle` and/or `regime` (type `Literal["bundle","regime"]`). Single-key grouping → string key; multi-key → tuple in `group_by` order. **A3 hallmark**: there is no `"symbol"` grouping option; tests assert no key (or tuple component) is ever a symbol. Stats math: expectancy = mean R, win_rate = fraction R>0, sharpe_raw = mean/std (sample std, ddof=1; guarded to 0.0 when std==0 or n<2), CI = mean ± 1.96·std/√n (normal approx). `eligible_for_ranking()` is a **separate view** that filters `n < settings.bundle_min_n` (20) — all stats are still computed; only ranking-eligibility is gated, per spec §4.
   - `stats_from_trades` is a module-level helper reused by `WalkForward.stats` to keep the math single-source.

4. **`PerRegimeStatStore`** (B14) — `upsert` is idempotent on `(bundle, regime, as_of_date)`: updates in place when the row exists, inserts otherwise. Maps `BundleStats` → `BundleStatPerRegime`: `sharpe_raw` → `oos_sharpe_shrunk` **clamped to [-3, 3]** to satisfy the DB CheckConstraint (`test_sharpe_clamped_to_range`). `latest()` returns the most recent row by `as_of_date` or `None`.

## Notes / boundaries respected

- Did **not** modify `shared/types.py`, `settings.py`, or `models.py`. Used existing `BundleStats`, `BacktestTrade`, `bundle_min_n`, and the `BundleStatPerRegime` ORM as-is.
- `from __future__ import annotations` in every file; full type hints; no `float ==` in production code (tests use `pytest.approx`); A3 tests marked `@pytest.mark.hallmark`.
- The `oos_sharpe_shrunk` column receives the (clamped) raw Sharpe from `BundleStats.sharpe_raw`. The actual shrinkage step (`shrunk_sharpe`) is a separate function the runner/selector layer is expected to apply before constructing the `BundleStats` it persists. This matches the module split in spec §1 (shrinkage and per_regime are distinct files); no cross-wiring was in scope for this task.

## No blockers.

## Recommended next step

Wire `shrunk_sharpe` into the runner/selection layer (`selection.py`, `runner.py`) so the value persisted via `PerRegimeStatStore.upsert` is the shrunk Sharpe rather than raw — that integration is owned by the runner task, not this one.
