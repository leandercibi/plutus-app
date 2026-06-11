# P1 — Swing Entry Gates (spec 07 §9) — Implementation Report

Branch: `v2-rebuild` · TDD · all tests written before implementation.

## Status: COMPLETE — 23/23 tests pass, ruff clean, mypy --strict clean

## Modules implemented (`src/plutus/swing/entries/`)

| File | Class / API | Review item |
|---|---|---|
| `volume_gate.py` | `VolumeGate.passes(candles, delivery, today_idx, is_expiry_day=False) -> bool` | A9 |
| `circuit_gate.py` | `CircuitGate.status(symbol, candles, lookback_sessions=90) -> CircuitStatus` | B7 |
| `earnings_gate.py` | `EarningsGate.evaluate(signal, earnings_in_window, atr) -> EarningsAdjustment` | B6 |
| `monday_revalidation.py` | `MondayRevalidation.reevaluate(sunday_signal, monday_open, atr, hard_kill_fires) -> RevalidationOutcome` | A15 |
| `gate.py` | `EntryGate.evaluate(signal, ctx) -> EntryDecision` | composes §9 order |

### Frozen dataclasses defined
- `CircuitStatus(hit_count, last_hit_date, suppress)`
- `EarningsAdjustment(action, downgrade, adjusted_stop, widen_stop_option, downgrade_option)`
- `RevalidationOutcome(keep, reason)`
- `EntryContext(candles, delivery, today_idx, earnings_in_window, atr, circuit_suppress, is_expiry_day)`
- `EntryDecision(allowed, reasons, adjusted_signal)`

## Key design decisions

1. **VolumeGate (A9):** delivery-adjusted volume = `traded_qty * delivery_pct`. Confirmation candle must be **strictly greater** than `settings.volume_gate_delivery_mult` (1.3) × 20-day median. Expiry/rebalance day → returns `True` unconditionally (gate not applied), via either an `is_expiry_day` arg OR an `is_expiry_or_rebalance_day` column in the delivery frame.

2. **CircuitGate (B7):** a bar is a circuit hit when locked (`high == low`) OR absolute move from prior close ≥ `circuit_pct` (constructor arg, default 0.20 — not hardcoded in the comparison path; `circuit_pct` is configurable, e.g. 0.05). Only hits within `lookback_sessions` count. Any hit → `suppress=True`.

3. **EarningsGate (B6):** never kills. `policy` constructor arg ("downgrade" | "widen_stop"). Widen = `stop_loss - settings.earnings_stop_widen_atr (1.0) * atr`. **Both** options always recorded (`widen_stop_option`, `downgrade_option`) regardless of active policy. Outside window → `action="pass"`.

4. **MondayRevalidation (A15):** kill if `abs(monday_open - entry) > settings.monday_gap_kill_atr_mult (1.0) * atr` (strictly greater; gap == 1 ATR is kept). Hard-kill flag → kill. Else keep. Gap-down handled by absolute value.

5. **EntryGate (§9 order):** Circuit → Earnings(adjust) → Volume → heat → sector → corr → adv → cooldown. The five risk/cooldown gates are injected as objects exposing `.check(signal, ctx) -> bool`; first failure short-circuits. Circuit & volume failures short-circuit **before** any risk gate is consulted (verified with spy stubs asserting call order `[]` on early failure, `["heat","sector","corr","adv","cooldown"]` on full pass). Earnings widening mutates `adjusted_signal.stop_loss` without killing.

## Tests (`tests/swing/entries/`) — 23 cases
- `test_volume_gate.py` (5): >1.3× pass; <1.3× fail; expiry arg skip; expiry column skip; exact 1.3× boundary fails.
- `test_circuit_gate.py` (4): no hits → no suppress; locked-limit hit in-window → suppress + correct date; hit outside lookback ignored; configurable circuit_pct.
- `test_earnings_gate.py` (4): outside → pass; widen_stop policy; downgrade policy; both options recorded.
- `test_monday_revalidation.py` (5): gap>1ATR kill; hard-kill; clean keep; gap==1ATR keep; gap-down kill.
- `test_entry_gate_order.py` (5): §9 order; circuit short-circuit before heat; volume short-circuit before heat; heat failure stops remaining gates; earnings adjusts signal without killing.

## Verification commands run
```
.venv/bin/python -m pytest tests/swing/entries/ -q   → 23 passed
.venv/bin/ruff check src/plutus/swing/entries tests/swing/entries → All checks passed
.venv/bin/mypy --config-file mypy.ini src/plutus/swing/entries → Success: no issues (6 files)
```
Regression: `tests/swing/entries + scoring + sizing` → 46 passed.

## Constraints honored
- `from __future__ import annotations`, full type hints, `Decimal` for all prices, no float `==`, no magic numbers in logic (all thresholds from `settings` or named constructor args / module constants like `_MEDIAN_WINDOW=20`).
- **Did NOT modify** `settings.py` or `types.py`. (Note: `git status` shows `settings.py` as modified — that change was made by the parent/orchestrator before delegation to add the entry-gate settings fields I consume; I did not touch it.)

## Blockers / notes
- None for this task. All required `settings` fields pre-existed.
- `data/delivery.py` (the `delivery_adjusted_volume` / `is_expiry_or_rebalance_day` helpers, spec 04 §5) does not exist yet — owned by the data-pipeline worker. To stay self-contained I compute delivery-adjusted volume inline in `VolumeGate` and accept the expiry flag via arg/column. When `data/delivery.py` lands, `VolumeGate` could optionally delegate, but no change is required for correctness.
- `tests/swing/bundles/test_vcp.py` errors on collection (`plutus.swing.bundles.vcp` missing) — that is another worker's in-flight bundles scope, not mine; my suite runs clean in isolation.
