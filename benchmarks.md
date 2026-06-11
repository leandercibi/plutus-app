# Benchmarks (B2) — Implementation Report

Branch: `v2-rebuild`. Status: **COMPLETE — all green.**

## Verification
- `.venv/bin/python -m pytest tests/shared/benchmarks/ -q` → **13 passed**
- `.venv/bin/mypy --config-file mypy.ini src/plutus/shared/benchmarks/` → **Success, no issues** (5 source files)
- `.venv/bin/ruff check src/plutus/shared/benchmarks/` → **All checks passed**

## Files created

Source:
- `src/plutus/shared/benchmarks/nifty_buy_hold.py` — `NiftyBuyHold.equity_curve(start, end, nifty_closes)` → normalized curve (1.0 at start), window-clipped.
- `src/plutus/shared/benchmarks/regime_switched.py` — `RegimeSwitched.equity_curve(start, end, nifty_closes, regime_history)` → captures Nifty daily return only when prior day label is BULL; flat (cash) otherwise.
- `src/plutus/shared/benchmarks/random_liquid.py` — `RandomLiquidBaseline(seed=42)`; `matched_picks(...)` and `matched_trade_curve(plutus_trades, universe_at, returns_for)`. Same trade count, same hold windows, deterministic via `np.random.default_rng(seed)`.
- `src/plutus/shared/benchmarks/strip.py` — `BenchmarkResult` (frozen dataclass) + `BenchmarkStrip.compute(...)` → four net_pct numbers + profit factor + n_trades.

Tests:
- `tests/shared/benchmarks/test_nifty_buy_hold.py` (3)
- `tests/shared/benchmarks/test_regime_switched.py` (3)
- `tests/shared/benchmarks/test_random_liquid_matched.py` (3)
- `tests/shared/benchmarks/test_random_liquid_no_lookahead.py` (1)
- `tests/shared/benchmarks/test_benchmark_strip.py` (3)

## Decisions & deviations (surfaced, not silent)
1. **Signatures follow the TASK contract, not spec §7 verbatim.** The task explicitly required passing price series / curves / callables in as arguments for testability (no live data fetch), and the spec's `BenchmarkStrip.compute(result: BacktestResult)` references a `BacktestResult` type that does not exist yet. I therefore took `plutus_trades` + the four equity curves directly. When the runner/`BacktestResult` lands, a thin adapter can call `BenchmarkStrip.compute` from a `BacktestResult`.
2. **RegimeSwitched return convention:** a day's Nifty return is captured only if the *prior* day's regime label is BULL (you must be long going into the day to earn it). All-BULL exactly reproduces the buy-hold curve; all-BEAR stays flat at 1.0. This is the natural, look-ahead-free reading of "long Nifty when BULL; cash otherwise."
3. **`matched_picks` extracted as a public method** so the no-lookahead test can assert the chosen symbol was in `universe_at(entry_date)` without re-deriving randomness. `matched_trade_curve` reuses it.
4. **Profit factor edge cases:** no losses + some wins → `inf`; no wins and no losses → `0.0`.
5. **`cast("pd.Series", ...)`** added in `nifty_buy_hold.py` to satisfy mypy strict (pandas `__truediv__` returns `Any`).

## Constraints honored
- `from __future__ import annotations`, full type hints, `np.random.default_rng(seed)`, `pytest.approx` (no float `==`), date-indexed pandas Series.
- Touched only `benchmarks/` + `tests/shared/benchmarks/`. **Did NOT modify `shared/types.py`** — `BacktestTrade` was sufficient as-is.

## Open risks / next steps
- Adapter to call `BenchmarkStrip.compute` from a future `BacktestResult` (runner work, out of this task's scope).
- `random_liquid` "similar liquidity" matching from spec §7.3 is simplified to uniform pick within the PIT universe; liquidity-stratified sampling can be layered later if a liquidity accessor becomes available (would need a new callable — flagged, not silently added).
