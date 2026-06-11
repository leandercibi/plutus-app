# P1 Swing Bundles — Implementation Report

Branch: `v2-rebuild` · Spec: `specs/v2/07_swing_domain.md` §2–§3, §13.1

## Status: COMPLETE — all green

- **34 tests pass** (`tests/swing/bundles/`)
- **mypy --strict**: clean (10 source files)
- **ruff**: clean
- **coverage**: 94% on `src/plutus/swing/bundles/` (composite 100%, all others ≥91%)
- Full `tests/swing/` suite (125 tests) passes — no regressions to existing P0 scoring modules.

## Modules implemented (TDD: test written first, then impl)

| Module | Setup (faithful to spec §3) | Geometry |
|---|---|---|
| `trend.py` `TrendBundle` | 50DMA>200DMA; price within 1 ATR of 50DMA; delivery-adjusted volume contraction during pullback | stop = pullback low − 0.5 ATR; T1 = recent swing high; T2 = entry + 1.5·risk |
| `breakout.py` `BreakoutBundle` | Donchian-20 high cleared; delivery-adjusted volume > 1.5× 20d median | stop = donchian high − 1.5 ATR; T1=1.5R; T2=2.5R. **B7**: `ctx.extras['circuit_recent_hit']` → None unless move > `settings.breakout_strong_atr_mult` (2.0) ATR |
| `reversal.py` `ReversalBundle` | 5 closes below 20DMA; bullish engulfing; delivery-adjusted volume confirm | stop = engulf low − 0.5 ATR; T1=1.5R; T2=2.5R |
| `vcp.py` `VCPBundle` | ≥3 contractions of decreasing amplitude on declining volume; breakout on expanding delivery-adjusted volume | stop = final-contraction high − 0.5 ATR; T1=2R; T2=3R. **B7**: `ctx.extras['circuit_bars']` (set of indices) excluded from contraction count |
| `composite.py` `CompositeBundle` | A5 — aggregates ≥2 agreeing sub-bundles (trend/breakout/vcp/reversal) | `widest_stop` + `probability_weighted_target` from existing `composite_geometry.py`; 1 sub → None; 3 → median stop. Exposes `combine(sub_signals)` + `fit_signal` (reads `ctx.extras['sub_signals']`) |
| `pead.py` `PEADBundle` | C2 gated — requires `ctx.extras['earnings_in_last_5_sessions']` AND `['verified_earnings']` | paper-only by default; signal carries `'paper_only'` in `reasons` |
| `smc.py` `SMCBundle` | C3 gated — order-block reclaim | produces a `bundle='smc'` signal flagged `'display_only'` (selector exclusion tested elsewhere) |

Shared helper added: `src/plutus/swing/bundles/_indicators.py` (`sma`, `atr`, `delivery_adjusted_volume`) — new file, no forbidden-file edits.

## Contracts honored
- Used existing `BaseBundle`/`BundleContext`/`RequiredInput` (base.py), `BundleSignal` (types.py), `widest_stop`/`probability_weighted_target` (composite_geometry.py), `StubCalibration` (tests). **None modified.**
- All prices `Decimal`; `from __future__ import annotations`; full type hints; no float `==` (used `pytest.approx`); thresholds via `settings` (no magic numbers in risk-bearing logic).
- Fixtures are hand-built deterministic pandas DataFrames; no live data.

## Test-case coverage vs spec §13.1
- trend: clean pullback→signal w/ stop below pullback low ✓; no-pullback→None ✓; downtrend→None ✓
- breakout: break+volume→signal ✓; no volume→None ✓; circuit-hit→None unless >2 ATR ✓
- reversal: engulfing after 5 down closes + delivery confirm→signal ✓; no delivery confirm→None ✓
- vcp: 3 contractions→signal ✓; circuit-affected bars excluded→None ✓
- composite: 2 agreeing→widest stop ✓; 1→None ✓; 3→median ✓; prob-weighted target manual match ✓
- pead: no earnings→None ✓; earnings+verified→paper_only signal ✓ (+ unverified→None)
- smc: produces `bundle='smc'` signal ✓

## Notes / minor deviations (non-blocking)
- Spec §3.1 says trend T1 = recent swing high. When the swing high sits far above entry, T2 (entry+1.5·risk) can be **below** T1 — this is correct per the spec formulas, so the trend test asserts both targets are above entry rather than T2>T1.
- Composite's primary API is `combine(sub_signals)`; `fit_signal` is the BaseBundle-contract wrapper that pulls sub-signals from `ctx.extras['sub_signals']`. Constructor takes `(calibration, regime)` as instructed.
- VCP contraction detection is a deterministic windowed heuristic (mean high-low range + mean volume per `_CONTRACTION_LEN`=8 window, requiring monotonic decrease across the last 3 windows). Faithful to the spec intent; tunable later.

## Blockers
None. No changes needed to `base.py`, `types.py`, `composite_geometry.py`, or `settings.py` (the `breakout_strong_atr_mult` field already existed).

## Verify command
```
.venv/bin/python -m pytest tests/swing/bundles/ -q          # 34 passed
.venv/bin/mypy --config-file mypy.ini src/plutus/swing/bundles   # clean
.venv/bin/ruff check src/plutus/swing/bundles tests/swing/bundles # clean
```
