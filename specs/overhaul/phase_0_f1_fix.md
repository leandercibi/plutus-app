# Phase 0 — F1 Backtest Data Validation Fix

```yaml
phase_id: phase_0
status: pending
depends_on: []
blocks: [phase_1, phase_2, phase_4a, phase_4b, phase_5, dashboard]
estimated_effort: 1 day
test_framework: pytest
```

## Goal

The Strategy Lab backtest returns nonsensical results (`Sharpe -93` for RELIANCE Trend 90d, per `PM_REVIEW.md:62`) because yfinance / jugaad-data sometimes return 0–10 bars instead of 90. The strategy then warms up indicators on near-empty data and emits 0–2 garbage trades. Tests for the fix are already written (`tests/test_phase2_f1_backtest.py`); production code needs to catch up to the contract.

After this phase: every fetch of OHLCV announces how many bars it actually got, the backtest runner refuses to run on insufficient data, and `RELIANCE` Trend 90d returns a `Sharpe ∈ [-2, +3]` with `trades ≥ 5`.

## Acceptance criteria

- [ ] `pytest tests/test_phase2_f1_backtest.py` — all 13 tests green
- [ ] `df.attrs["bars_fetched"]` and `df.attrs["bars_requested"]` set by every code path in `fetch_ohlcv()` (jugaad, Angel, yfinance, cache hit, empty)
- [ ] `run_bundle()` raises `InsufficientDataError` (never silently returns `_empty_result`) when bars < `MIN_BARS_REQUIRED`
- [ ] `InsufficientDataError` is NOT swallowed by the broad `except Exception` at `src/plutus/backtesting/runner.py:92`
- [ ] Manual: `python -c "from plutus.backtesting.runner import run_bundle; print(run_bundle('RELIANCE', 'trend', days=90))"` produces a `BundleResult` with `sharpe_ratio ∈ [-2, +3]`, `total_trades ≥ 5`

## Prerequisites

None. This is the foundation phase.

## Task list

### TASK-0.1 — Confirm the test contract

```yaml
parallelizable: no
parallel_group: null
reason: Reading the test fixes the contract; everything else depends on this understanding.
estimated_effort: 15min
```

**Test first** (TDD — read the existing tests, do NOT modify them):
- Open `tests/test_phase2_f1_backtest.py`
- Verify the 13 tests cover: metadata population, error message contents, error attribute names, run_bundle behaviour, sharpe clamp, zero-trades, valid backtest, trade-log fields, sanity ranges.
- Confirm `MIN_BARS_REQUIRED == 60` (`tests/test_phase2_f1_backtest.py:145`).

**Implementation**: None — read-only.

**Acceptance**:
- [ ] Test inventory documented in PR description
- [ ] No changes to tests/

---

### TASK-0.2 — Populate `df.attrs` in `fetch_ohlcv()`

```yaml
parallelizable: no
parallel_group: null
reason: All other Phase 0 tasks depend on this metadata being present.
estimated_effort: 1h
```

**Test first** (already exists — must pass after this task):
```python
# tests/test_phase2_f1_backtest.py:40-52
def test_fetch_returns_bar_count_metadata(self):
    df = _make_fetch_mock(90)
    assert df.attrs["bars_fetched"] == 90
    assert df.attrs["bars_requested"] == 90

def test_fetch_empty_returns_zero_bars(self):
    df = _make_fetch_mock(0)
    assert df.attrs["bars_fetched"] == 0

def test_fetch_partial_returns_actual_count(self):
    df = _make_fetch_mock(30, requested=90)
    assert df.attrs["bars_fetched"] == 30
    assert df.attrs["bars_requested"] == 90
```

**Add new direct-call test** (a real-fetch path is mocked above, but we also need the live `fetch_ohlcv` to populate `attrs`):
```python
# tests/test_phase0_attrs.py (new)
import pandas as pd
from unittest.mock import patch
from plutus.data.ohlcv import fetch_ohlcv

def test_fetch_ohlcv_populates_attrs_on_success(monkeypatch):
    fake = pd.DataFrame({"Open": [1]*90, "High": [1]*90, "Low": [1]*90, "Close": [1]*90, "Volume": [1]*90},
                       index=pd.date_range("2024-01-01", periods=90, freq="B"))
    monkeypatch.setattr("plutus.data.ohlcv._fetch_jugaad", lambda *a, **kw: fake)
    df = fetch_ohlcv("RELIANCE", days=90, interval="1d")
    assert df.attrs["bars_fetched"] == 90
    assert df.attrs["bars_requested"] == 90

def test_fetch_ohlcv_populates_attrs_on_empty(monkeypatch):
    monkeypatch.setattr("plutus.data.ohlcv._fetch_jugaad", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr("plutus.data.ohlcv._fetch_angelone", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr("plutus.data.ohlcv._fetch_yfinance", lambda *a, **kw: pd.DataFrame())
    df = fetch_ohlcv("BADTICKER", days=90, interval="1d")
    assert df.attrs["bars_fetched"] == 0
    assert df.attrs["bars_requested"] == 90

def test_fetch_ohlcv_populates_attrs_on_cache_hit(tmp_path, monkeypatch):
    # set up cache hit and verify attrs survive
    ...
```

**Files to modify**:
- `src/plutus/data/ohlcv.py:205–254` (function `fetch_ohlcv`) — at every return point set:
  ```python
  df.attrs["bars_fetched"] = len(df)
  df.attrs["bars_requested"] = days
  return df
  ```
- `src/plutus/data/ohlcv.py:131–138` (`_write_cache`) — preserve `attrs` when reading back from parquet (parquet does NOT preserve `attrs` by default; either persist them in a sidecar or recompute on cache read at `_read_cache`).

**Implementation steps**:
1. Add a single helper `_tag_df(df, days)` that sets both attrs and returns the df.
2. Wrap every return statement in `fetch_ohlcv` with `_tag_df(df, days)`.
3. In `_read_cache`, recompute attrs from the loaded df before returning.

**Acceptance**:
- [ ] All three new tests green
- [ ] `test_fetch_returns_bar_count_metadata`, `test_fetch_empty_returns_zero_bars`, `test_fetch_partial_returns_actual_count` green

---

### TASK-0.3 — Tighten exception handling in `run_bundle`

```yaml
parallelizable: no
parallel_group: null
reason: Depends on TASK-0.2 (attrs must exist to compute bar count reliably).
estimated_effort: 30min
```

**Test first** (already exists):
```python
# tests/test_phase2_f1_backtest.py:70-76
def test_insufficient_bars_raises_error(self):
    short_df = _make_fetch_mock(30)
    with patch("plutus.backtesting.runner.fetch_ohlcv", return_value=short_df):
        with pytest.raises(InsufficientDataError) as exc_info:
            run_bundle("TEST", "trend", days=30)
        assert exc_info.value.bars_fetched == 30
        assert exc_info.value.bars_required == MIN_BARS_REQUIRED
```

**Add a new regression test** (the bug we're fixing — broad `except Exception` swallowing data errors):
```python
# tests/test_phase0_exception.py (new)
from unittest.mock import patch
import pytest
from plutus.data.ohlcv import InsufficientDataError
from plutus.backtesting.runner import run_bundle

def test_insufficient_data_error_not_swallowed(monkeypatch):
    """Regression: the broad except Exception at runner.py:92 must NOT eat InsufficientDataError."""
    # Force fetch_ohlcv to return a too-short df
    import pandas as pd
    short = pd.DataFrame({"Open":[1]*10}, index=pd.date_range("2024-01-01", periods=10, freq="B"))
    short.attrs["bars_fetched"] = 10
    short.attrs["bars_requested"] = 90
    with patch("plutus.backtesting.runner.fetch_ohlcv", return_value=short):
        with pytest.raises(InsufficientDataError):
            run_bundle("TEST", "trend", days=90)
```

**Files to modify**:
- `src/plutus/backtesting/runner.py:60–95` (function `run_bundle`) — the current code at line 90–91 re-raises `InsufficientDataError`, but the bare `except Exception` at line 92 could mask other data-quality errors. After this task the structure should be:

  ```python
  def run_bundle(symbol, bundle_name, days=90):
      if bundle_name not in BUNDLE_MAP:
          raise ValueError(f"Unknown bundle: {bundle_name}")

      df = fetch_ohlcv(symbol, days=days, interval="1d")
      bars = df.attrs.get("bars_fetched", len(df) if df is not None else 0)

      if bars < MIN_BARS_REQUIRED:
          raise InsufficientDataError(bars, MIN_BARS_REQUIRED, symbol)

      warnings = []
      if bars < days:
          warnings.append(f"Only {bars}/{days} bars available — results may be less reliable")

      try:
          engine = bt.Cerebro(stdstats=False)
          engine.addstrategy(BUNDLE_MAP[bundle_name])
          ...
          result = _summarise(bundle_name, strat)
          result.warnings.extend(warnings)
          return result
      except Exception:
          log.exception("run_bundle: cerebro failure symbol=%s bundle=%s", symbol, bundle_name)
          return _empty_result(bundle_name)
  ```

  Key change: data validation lives **outside** the try-block. The try only wraps Cerebro execution.

**Implementation steps**:
1. Move the `fetch_ohlcv` call out of `try`.
2. Move the `InsufficientDataError` raise out of `try`.
3. The `try/except Exception` now only wraps `bt.Cerebro` invocation.
4. The `except InsufficientDataError: raise` at line 90–91 becomes unreachable and can be deleted.

**Acceptance**:
- [ ] `test_insufficient_bars_raises_error` green
- [ ] New `test_insufficient_data_error_not_swallowed` green
- [ ] `test_exactly_min_bars_does_not_raise` green
- [ ] `test_partial_bars_returns_warning` green

---

### TASK-0.4 — Run the full F1 test suite

```yaml
parallelizable: no
parallel_group: null
reason: Gate before manual smoke test.
estimated_effort: 10min
```

**Command**:
```bash
pytest tests/test_phase2_f1_backtest.py tests/test_phase0_attrs.py tests/test_phase0_exception.py -v
```

**Expected**: all green.

**If red**: do NOT proceed. Reopen the failing test and fix.

**Acceptance**:
- [ ] 13 tests in `test_phase2_f1_backtest.py` green
- [ ] New phase-0 tests green
- [ ] No skipped tests (skips indicate a partial implementation)

---

### TASK-0.5 — Manual smoke test on RELIANCE

```yaml
parallelizable: no
parallel_group: null
reason: Final acceptance against PRD success criterion (specs/PRD_PHASE2.md:73).
estimated_effort: 10min
```

**Command**:
```bash
python -c "
from plutus.backtesting.runner import run_bundle
r = run_bundle('RELIANCE', 'trend', days=90)
print(f'Sharpe={r.sharpe_ratio}, trades={r.total_trades}, win_rate={r.win_rate}, suspect={r.suspect}')
print('warnings:', r.warnings)
"
```

**Expected output** (per `specs/PRD_PHASE2.md:73`):
- `sharpe_ratio` ∈ [-2.0, +3.0]
- `total_trades` ≥ 5
- `win_rate` ∈ [0.30, 0.70]
- `suspect == False`

**Acceptance**:
- [ ] Output matches expected ranges
- [ ] Result captured in PR description for audit

## Streamlit considerations

None. Phase 0 is data-layer + backtest runner only. The Strategy Lab UI surface lands in the dashboard phase.

## Verification

```bash
# Full Phase 0 gate
pytest tests/test_phase2_f1_backtest.py tests/test_phase0_attrs.py tests/test_phase0_exception.py -v
python scripts/smoke_phase0_reliance.py    # wrap TASK-0.5 in a script for repeatability
```

Expected: all green, smoke output matches PRD ranges.

## Done definition

- [ ] TASK-0.1 through TASK-0.5 complete
- [ ] All Phase 0 tests green
- [ ] Manual smoke test recorded
- [ ] `README.md` updated: Phase 0 status → `done`
- [ ] Phase 1, 2, 4a, 4b unblocked

## References

- Plan: `/Users/leander/.claude/plans/first-the-scale-you-hazy-naur.md` (Phase 0 section)
- Test contract: `tests/test_phase2_f1_backtest.py`
- PRD success criterion: `specs/PRD_PHASE2.md:73`
- Code anchors:
  - `src/plutus/data/ohlcv.py:84` — `InsufficientDataError` class definition
  - `src/plutus/data/ohlcv.py:205` — `fetch_ohlcv` function
  - `src/plutus/backtesting/runner.py:29` — `MIN_BARS_REQUIRED = 60`
  - `src/plutus/backtesting/runner.py:60` — `run_bundle` function
- Reviewer signal: `PM_REVIEW.md:62` (Sharpe -93 report)
