# Phase 2 — Per-Bundle Hardening (5 bundles)

```yaml
phase_id: phase_2
status: pending
depends_on: [phase_0, phase_3a]
blocks: [phase_5]
estimated_effort: 4 days
test_framework: pytest
```

## Goal

Each of the 5 existing strategy bundles (`bundle_trend`, `bundle_reversal`, `bundle_breakout`, `bundle_smc`, `bundle_composite`) currently emits signals with hardcoded stops/targets and no volume/regime gating. After this phase: ATR-based stops/targets, volume confirmation requirement, regime-aware filtering, and `SMC` rebuilt around measurable BOS (Break of Structure) / CHOCH (Change of Character) primitives. The R:R floor moves from 1.5 → 2.0 at the bundle level so weak setups are dropped before they reach the scorer.

## Acceptance criteria

- [ ] Every signal from every bundle has `stop = entry - 1.5*ATR(14)` (long) or `entry + 1.5*ATR` (short)
- [ ] Every signal has `T1 = entry + 2*ATR` and `T2 = entry + 3*ATR` (longs; mirror for shorts)
- [ ] No signal emits with `Volume_Ratio < 1.3` on the setup bar
- [ ] `TrendBundle` emits longs only in `BULL` regime; `ReversalBundle` only in `RANGING`; `BreakoutBundle` requires sector RS in top 3
- [ ] SMC bundle has unit tests for BOS and CHOCH detection on synthetic data
- [ ] R:R floor of 2.0 enforced before signal emission
- [ ] All bundle tests green; backtest on RELIANCE/HDFCBANK produces non-empty trade logs for ≥ 3 of the 5 bundles

## Prerequisites

- Phase 0 done — backtest infra honest about data
- Phase 3a done — `get_nifty_regime()` and `get_sector_strength()` callable

## Task list

### TASK-2.1 — Extract shared bundle helpers

```yaml
parallelizable: no
parallel_group: null
reason: All 5 bundles depend on these shared utilities.
estimated_effort: 3h
```

**Test first**:
```python
# tests/test_strategies/test_helpers.py
from plutus.strategies.helpers import atr_levels, volume_gate_passes, regime_gate_passes, rr_ratio_above

def test_atr_levels_long():
    stop, t1, t2 = atr_levels(entry=100.0, atr=2.0, side="long")
    assert stop == pytest.approx(97.0)
    assert t1 == pytest.approx(104.0)
    assert t2 == pytest.approx(106.0)

def test_atr_levels_short():
    stop, t1, t2 = atr_levels(entry=100.0, atr=2.0, side="short")
    assert stop == pytest.approx(103.0)
    assert t1 == pytest.approx(96.0)

def test_volume_gate_threshold():
    assert volume_gate_passes(volume_ratio=1.5) is True
    assert volume_gate_passes(volume_ratio=1.3) is True
    assert volume_gate_passes(volume_ratio=1.29) is False

def test_regime_gate_trend_bullish():
    assert regime_gate_passes(bundle="trend", regime="BULL") is True
    assert regime_gate_passes(bundle="trend", regime="BEAR") is False

def test_rr_ratio_above_floor():
    assert rr_ratio_above(entry=100, stop=98, t1=104, floor=2.0) is True   # R:R = 2.0
    assert rr_ratio_above(entry=100, stop=98, t1=103.5, floor=2.0) is False
```

**Files to create**:
- `src/plutus/strategies/helpers.py` — pure functions consumed by every bundle.

**Acceptance**:
- [ ] All helper tests green
- [ ] Helpers contain zero side effects (no DB writes, no fetches)

---

### Parallel group 2A — Bundle rewrites (TASK-2.2 through TASK-2.5)

The four "simple" bundles can be hardened in parallel — they share helpers but no code paths.

### TASK-2.2 — Harden `TrendBundle`

```yaml
parallelizable: yes
parallel_group: 2A
reason: Independent file; helpers stable from TASK-2.1.
estimated_effort: 3h
```

**Test first**:
```python
# tests/test_strategies/test_bundle_trend.py
from plutus.strategies.bundle_trend import TrendBundle

def test_trend_bundle_emits_only_in_bull(synthetic_uptrend_df, monkeypatch):
    monkeypatch.setattr("plutus.data.regime.get_nifty_regime", lambda: {"trend": "BULL"})
    signals = run_bundle_collect(TrendBundle, synthetic_uptrend_df)
    assert len(signals) >= 1

def test_trend_bundle_skips_in_bear(synthetic_uptrend_df, monkeypatch):
    monkeypatch.setattr("plutus.data.regime.get_nifty_regime", lambda: {"trend": "BEAR"})
    signals = run_bundle_collect(TrendBundle, synthetic_uptrend_df)
    assert len(signals) == 0

def test_trend_bundle_skips_low_volume(synthetic_low_volume_df):
    signals = run_bundle_collect(TrendBundle, synthetic_low_volume_df)
    assert len(signals) == 0

def test_trend_bundle_atr_stops(synthetic_uptrend_df):
    signals = run_bundle_collect(TrendBundle, synthetic_uptrend_df)
    for sig in signals:
        atr = sig.atr_at_entry
        assert abs(sig.entry - sig.stop) == pytest.approx(1.5 * atr, rel=0.05)
        assert abs(sig.t1 - sig.entry) == pytest.approx(2.0 * atr, rel=0.05)

def test_trend_bundle_rejects_low_rr(synthetic_tight_target_df):
    """If target is too close, RR<2 — signal must be skipped."""
    signals = run_bundle_collect(TrendBundle, synthetic_tight_target_df)
    assert len(signals) == 0
```

**Files to modify**:
- `src/plutus/strategies/bundle_trend.py` — adopt `helpers.atr_levels`, `volume_gate_passes`, `regime_gate_passes`, `rr_ratio_above`.

**Acceptance**:
- [ ] Five tests green
- [ ] Backtest on RELIANCE 90d produces ≥ 3 trades, all with ATR-anchored stops

---

### TASK-2.3 — Harden `ReversalBundle`

```yaml
parallelizable: yes
parallel_group: 2A
reason: Independent file.
estimated_effort: 3h
```

**Test first** (mirror TASK-2.2 with `RANGING` regime):
```python
def test_reversal_bundle_emits_in_ranging(monkeypatch, synthetic_oversold_bounce_df):
    monkeypatch.setattr("plutus.data.regime.get_nifty_regime", lambda: {"trend": "SIDEWAYS"})
    signals = run_bundle_collect(ReversalBundle, synthetic_oversold_bounce_df)
    assert len(signals) >= 1

def test_reversal_bundle_skips_in_strong_trend(monkeypatch, synthetic_oversold_bounce_df):
    monkeypatch.setattr("plutus.data.regime.get_nifty_regime", lambda: {"trend": "BULL", "slope": 0.8})
    # In a strong trend, mean-reversion plays are dangerous
    signals = run_bundle_collect(ReversalBundle, synthetic_oversold_bounce_df)
    assert len(signals) == 0
```

**Files to modify**: `src/plutus/strategies/bundle_reversal.py`.

**Acceptance**:
- [ ] Both regime-conditional tests green
- [ ] ATR/volume/RR gates green (use same pattern as TASK-2.2)

---

### TASK-2.4 — Harden `BreakoutBundle`

```yaml
parallelizable: yes
parallel_group: 2A
reason: Independent file.
estimated_effort: 3h
```

**Test first**:
```python
def test_breakout_requires_top_3_sector(monkeypatch, synthetic_breakout_df):
    monkeypatch.setattr("plutus.data.regime.get_sector_strength",
                        lambda: {"BANKING": 1.20, "IT": 1.15, "AUTO": 1.12, "PHARMA": 0.95})
    # If ticker is in BANKING (top 3) ⇒ signal emitted
    signals_banking = run_bundle_collect(BreakoutBundle, synthetic_breakout_df, sector="BANKING")
    assert len(signals_banking) >= 1
    # If ticker is in PHARMA (outside top 3) ⇒ no signal
    signals_pharma = run_bundle_collect(BreakoutBundle, synthetic_breakout_df, sector="PHARMA")
    assert len(signals_pharma) == 0

def test_breakout_requires_volume_spike(synthetic_breakout_low_volume_df):
    signals = run_bundle_collect(BreakoutBundle, synthetic_breakout_low_volume_df)
    assert len(signals) == 0
```

**Files to modify**: `src/plutus/strategies/bundle_breakout.py`.

**Acceptance**: tests green.

---

### TASK-2.5 — Harden `CompositeBundle`

```yaml
parallelizable: yes
parallel_group: 2A
reason: Independent file; consumes outputs of other bundles but tests with mocks.
estimated_effort: 2h
```

**Test first**:
```python
def test_composite_requires_3_of_4_agreement(monkeypatch):
    # Mock other bundles to return long-signal=True for 3 of 4
    ...
    signals = run_bundle_collect(CompositeBundle, df)
    assert len(signals) >= 1

def test_composite_emits_zero_when_only_2_agree():
    ...
    signals = run_bundle_collect(CompositeBundle, df)
    assert len(signals) == 0
```

**Files to modify**: `src/plutus/strategies/bundle_composite.py`.

**Acceptance**: tests green.

---

### TASK-2.6 — Rewrite `SMCBundle` with BOS + CHOCH

```yaml
parallelizable: no
parallel_group: null
reason: Non-trivial rewrite; sequential to avoid merging conflicts with Composite.
estimated_effort: 6h
```

**Test first** (TDD heavy — these tests define the new behaviour):
```python
# tests/test_strategies/test_bundle_smc.py
from plutus.strategies.smc_primitives import detect_swing_points, detect_bos, detect_choch

def test_detect_swing_points_on_synthetic():
    """5-bar fractal swing high/low detection."""
    df = make_zigzag_df()   # construct synthetic OHLC with known peaks/troughs
    highs, lows = detect_swing_points(df, lookback=5)
    assert len(highs) == 4 and len(lows) == 4

def test_bos_long_when_high_taken_out(uptrending_with_pullback_df):
    """BOS = break of structure: price breaks above the most recent swing high."""
    bos_events = detect_bos(uptrending_with_pullback_df, side="long")
    assert len(bos_events) >= 1
    assert bos_events[0]["bar_idx"] == 23   # known fixture position

def test_choch_signals_reversal(uptrend_then_reversal_df):
    """CHOCH = change of character: price breaks below the most recent swing low after uptrend."""
    choch_events = detect_choch(uptrend_then_reversal_df, side="long_to_short")
    assert len(choch_events) >= 1

def test_smc_bundle_signal_on_bos_then_pullback():
    """End-to-end: SMC long signal triggers on BOS + pullback to demand zone."""
    signals = run_bundle_collect(SMCBundle, smc_setup_df)
    assert len(signals) >= 1
    sig = signals[0]
    assert sig.bos_at_bar < sig.entry_bar
    assert sig.entry_zone[0] <= sig.entry <= sig.entry_zone[1]
```

**Files to create**:
- `src/plutus/strategies/smc_primitives.py` — `detect_swing_points`, `detect_bos`, `detect_choch` as pure functions.
- `src/plutus/strategies/bundle_smc.py` — replace existing logic. Entry = pullback to demand zone after BOS. Stop = below demand zone. Targets via ATR.

**Acceptance**:
- [ ] All four SMC tests green
- [ ] If walk-forward (Phase 4b) shows OOS Sharpe < 0, SMC bundle's weight in `CompositeBundle` is reduced to 0.5 (manual decision recorded in PR)

---

### TASK-2.7 — Lift R:R floor in legacy prompts

```yaml
parallelizable: yes
parallel_group: 2B
reason: Independent text edit.
estimated_effort: 10min
```

**Test first**:
```python
def test_no_legacy_rr_15_in_prompts():
    src = Path("src/plutus/agents/prompts.py").read_text()
    assert "1.5 R:R" not in src
    assert "R:R ratio < 1.5" not in src
```

**Files to modify**:
- `src/plutus/agents/prompts.py:26` (Technical) — change `1.5 R:R` → `2.0 R:R`
- `src/plutus/agents/prompts.py:100` (Risk Manager) — change `R:R ratio < 1.5` → `R:R ratio < 2.0`
- `src/plutus/config.py` — `min_rr_ratio: 1.5` → `2.0` (or expose via Phase 6 editable params)

**Acceptance**:
- [ ] Grep regression test green
- [ ] Bundle backtest does not re-introduce R:R<2 signals

---

### TASK-2.8 — Smoke test: 5 bundles × 5 fixture symbols

```yaml
parallelizable: no
parallel_group: null
reason: Final gate.
estimated_effort: 30min
```

**Command**:
```bash
python scripts/smoke_phase2_5x5.py
# Prints: bundle × symbol matrix of (trade_count, sharpe, avg_atr_stop_distance)
```

**Acceptance**:
- [ ] ≥ 3 of the 5 bundles produce ≥ 1 trade on RELIANCE 90d
- [ ] No signal has `R:R < 2.0`
- [ ] All ATR stop distances within ±5% of `1.5 * ATR(14)`

## Streamlit considerations

The Strategy Lab tab (`src/plutus/dashboard/strategy_lab.py` per PRD F1) consumes `BundleResult`. No schema change needed in this phase; the dashboard surfacing pass (`phase_dashboard.md`) handles UI updates.

## Verification

```bash
pytest tests/test_strategies/ -v
python scripts/smoke_phase2_5x5.py
```

## Done definition

- [ ] All 8 tasks complete
- [ ] All tests green
- [ ] Smoke output recorded in PR description
- [ ] `README.md` updated: Phase 2 status → `done`

## References

- Plan: Phase 2 section
- Code anchors:
  - `src/plutus/strategies/bundle_*.py` (5 files)
  - `src/plutus/agents/prompts.py:26,100` — legacy R:R floor
  - `src/plutus/data/ohlcv.py:320` — ATRr_14 column (input)
  - `src/plutus/data/ohlcv.py:326` — Volume_Ratio column (input)
- Related: [phase_3a_regime.md](phase_3a_regime.md), [phase_5_vcp_pead.md](phase_5_vcp_pead.md)
