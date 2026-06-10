# Phase 5 — VCP + PEAD Strategy Bundles

```yaml
phase_id: phase_5
status: pending
depends_on: [phase_2, phase_3b]
blocks: []
estimated_effort: 4 days
test_framework: pytest
```

## Goal

Add two empirically-validated edges to the existing 5-bundle set:

- **VCP** (Volatility Contraction Pattern, Minervini style) — detects 3+ tightening pullbacks before a breakout. Backtested edge in US large-caps; Indian midcaps show similar behaviour.
- **PEAD** (Post-Earnings Announcement Drift) — academic edge. Stocks that gap up >5% on earnings tend to drift higher 3–15 days. Requires earnings date data (Tickertape, Phase 3b).

Both register in `BUNDLE_MAP` (`runner.py:48`) but enter `CompositeBundle` only after walk-forward (Phase 4b) shows positive OOS Sharpe.

## Acceptance criteria

- [ ] `VCPBundle` produces ≥ 1 signal per 90-day window on the midcap universe
- [ ] `PEADBundle` produces ≥ 1 signal during Indian earnings windows (Jul/Oct/Jan/Apr)
- [ ] Both bundles use Phase 2 helpers (ATR stops, volume gate, R:R floor 2.0)
- [ ] Both registered in `BUNDLE_MAP`
- [ ] Tests cover detection logic on synthetic fixtures

## Prerequisites

- Phase 2 done — bundle hardening helpers exist
- Phase 3b done — `get_next_earnings_date()` callable

## Task list

### Parallel group 5A — Bundle implementations (TASK-5.1 and TASK-5.2)

The two bundles are independent.

### TASK-5.1 — `VCPBundle`

```yaml
parallelizable: yes
parallel_group: 5A
estimated_effort: 6h
```

**Test first**:
```python
# tests/test_strategies/test_bundle_vcp.py
from plutus.strategies.bundle_vcp import VCPBundle, detect_contractions, detect_pivot_breakout

def test_detect_contractions_3_tightening_pullbacks(synthetic_vcp_df):
    contractions = detect_contractions(synthetic_vcp_df, min_count=3)
    assert len(contractions) >= 3
    # Each pullback ATR should be smaller than previous
    atrs = [c["pullback_atr"] for c in contractions]
    assert all(atrs[i] > atrs[i+1] for i in range(len(atrs)-1))

def test_no_contractions_in_random_walk(synthetic_random_walk_df):
    contractions = detect_contractions(synthetic_random_walk_df, min_count=3)
    assert len(contractions) == 0

def test_pivot_breakout_with_volume(synthetic_vcp_with_breakout_df):
    """Triggers long on breakout above pivot with Volume_Ratio >= 1.5."""
    signals = run_bundle_collect(VCPBundle, synthetic_vcp_with_breakout_df)
    assert len(signals) >= 1
    sig = signals[0]
    assert sig.volume_ratio_at_breakout >= 1.5

def test_vcp_skipped_below_volume_threshold(synthetic_vcp_low_volume_df):
    signals = run_bundle_collect(VCPBundle, synthetic_vcp_low_volume_df)
    assert len(signals) == 0

def test_vcp_prefers_rsi_50_70(synthetic_vcp_rsi_85_df):
    """Overbought (RSI > 70) reduces conviction or skips."""
    signals = run_bundle_collect(VCPBundle, synthetic_vcp_rsi_85_df)
    assert len(signals) == 0

def test_vcp_atr_stops_match_phase2_helpers(synthetic_vcp_with_breakout_df):
    signals = run_bundle_collect(VCPBundle, synthetic_vcp_with_breakout_df)
    sig = signals[0]
    assert abs(sig.entry - sig.stop) == pytest.approx(1.5 * sig.atr_at_entry, rel=0.05)
```

**Files to create**:
- `src/plutus/strategies/bundle_vcp.py`:
  - `detect_contractions(df, min_count=3)` — pure function
  - `detect_pivot_breakout(df, contractions)` — pure function
  - `VCPBundle(bt.Strategy)` — backtrader strategy class

**Algorithm**:
1. Find swing highs/lows over 20-bar window.
2. Identify ≥ 3 consecutive contractions: each pullback's ATR < previous.
3. Mark pivot = last swing high before final contraction.
4. Trigger long when `Close > pivot AND Volume_Ratio >= 1.5 AND RSI ∈ [50, 70]`.
5. Apply Phase 2 helpers for stop/target/RR.

**Acceptance**: all 6 tests green.

---

### TASK-5.2 — `PEADBundle`

```yaml
parallelizable: yes
parallel_group: 5A
estimated_effort: 5h
```

**Test first**:
```python
# tests/test_strategies/test_bundle_pead.py
from plutus.strategies.bundle_pead import PEADBundle, detect_earnings_gap_up

def test_earnings_gap_5pct_detected(synthetic_earnings_gap_df, monkeypatch):
    monkeypatch.setattr("plutus.data.tickertape.get_next_earnings_date",
                        lambda s: date(2026, 7, 20))
    gaps = detect_earnings_gap_up(synthetic_earnings_gap_df, min_gap_pct=5.0)
    assert len(gaps) >= 1

def test_gap_below_5pct_skipped(synthetic_3pct_gap_df, monkeypatch):
    monkeypatch.setattr("plutus.data.tickertape.get_next_earnings_date",
                        lambda s: date(2026, 7, 20))
    gaps = detect_earnings_gap_up(synthetic_3pct_gap_df, min_gap_pct=5.0)
    assert len(gaps) == 0

def test_volume_2x_required(synthetic_gap_low_volume_df):
    signals = run_bundle_collect(PEADBundle, synthetic_gap_low_volume_df)
    assert len(signals) == 0

def test_entry_on_pullback_to_gap_fill(synthetic_pead_setup_df):
    """Triggers long when price pulls back to gap fill or 5/10 EMA, hold 3-15 days."""
    signals = run_bundle_collect(PEADBundle, synthetic_pead_setup_df)
    assert len(signals) >= 1
    sig = signals[0]
    assert sig.hold_days_min == 3
    assert sig.hold_days_max <= 15

def test_outside_indian_earnings_window_no_signal(synthetic_pead_setup_df, monkeypatch):
    """Earnings dates outside Jul/Oct/Jan/Apr ⇒ no signal."""
    monkeypatch.setattr("plutus.data.tickertape.get_next_earnings_date",
                        lambda s: date(2026, 6, 15))   # June, not earnings month
    signals = run_bundle_collect(PEADBundle, synthetic_pead_setup_df)
    assert len(signals) == 0
```

**Files to create**:
- `src/plutus/strategies/bundle_pead.py`:
  - `detect_earnings_gap_up(df, min_gap_pct=5.0)` — pure function
  - `PEADBundle(bt.Strategy)`

**Algorithm**:
1. Query `get_next_earnings_date(symbol)`.
2. If earnings within last 5 bars: check open gap up ≥ 5% AND volume ≥ 2× avg.
3. Wait for pullback to gap fill or 5/10 EMA.
4. Enter long; hold 3–15 days; ATR stop/target.

**Acceptance**: all 5 tests green.

---

### TASK-5.3 — Register in `BUNDLE_MAP`

```yaml
parallelizable: no
parallel_group: null
reason: Sequential after 5A.
estimated_effort: 15min
```

**Test first**:
```python
def test_bundle_map_includes_vcp_pead():
    from plutus.backtesting.runner import BUNDLE_MAP
    assert "vcp" in BUNDLE_MAP
    assert "pead" in BUNDLE_MAP
```

**Files to modify**: `src/plutus/backtesting/runner.py:48`.

---

### TASK-5.4 — Walk-forward validation (gate)

```yaml
parallelizable: no
parallel_group: null
reason: Required to confirm OOS validity before inclusion in Composite.
estimated_effort: 2h
```

**Command**:
```bash
python -m plutus.backtesting.walk_forward --symbol RELIANCE,INFY,HDFCBANK --bundle vcp --window 30 --step 7
python -m plutus.backtesting.walk_forward --symbol RELIANCE,INFY,HDFCBANK --bundle pead --window 30 --step 7
```

**Acceptance**:
- [ ] Both bundles' OOS Sharpe median > 0 on the 3-symbol fixture
- [ ] If OOS < 0: bundle stays in `BUNDLE_MAP` but NOT added to `CompositeBundle` weighting
- [ ] Decision recorded in PR description

## Streamlit considerations

Strategy Lab bundle dropdown automatically picks up new bundles from `BUNDLE_MAP`. No UI work.

## Verification

```bash
pytest tests/test_strategies/test_bundle_vcp.py tests/test_strategies/test_bundle_pead.py -v
python -m plutus.backtesting.runner --symbol RELIANCE --bundle vcp --days 90
python -m plutus.backtesting.runner --symbol INFY --bundle pead --days 90
```

## Done definition

- [ ] All 4 tasks complete; tests green
- [ ] Walk-forward decision recorded for both bundles
- [ ] `BUNDLE_MAP` updated

## References

- Plan: Phase 5 section
- Code anchors:
  - `src/plutus/backtesting/runner.py:48` — BUNDLE_MAP
  - `src/plutus/strategies/helpers.py` — Phase 2 helpers
  - `src/plutus/data/tickertape.py` — earnings date source
- External: Minervini VCP, Bernard & Thomas (1989) PEAD original paper
