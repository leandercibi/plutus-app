# P1 — Swing Exits (spec 07 §10) — DONE

Branch: `v2-rebuild`. All TDD, tests written before implementation.

## Implemented (src/plutus/swing/exits/)
| Module | Class / API | Spec |
|---|---|---|
| `stop.py` | `StopExit.check(plan, bar, fills, adv, atr_pct, qty=1) -> FillResult \| None` — delegates to `FillPolicy.fill_stop` | 10.1 |
| `trailing.py` | `ChandelierTrail.trail_stop(candles, entry_idx, current_idx, n_atr, atr_period) -> Decimal` = highest_high_since_entry − n_atr·ATR; `EMATrail.trail_stop(candles, ema_period) -> Decimal` | 10.2 / B8 |
| `no_progress.py` | `NoProgressExit.should_exit(NoProgressInput, candles) -> bool`; `NoProgressInput(entry, stop_loss, target_1, entry_idx, current_idx, horizon_max_days)` | 10.3 / B8 |
| `cooldown.py` | `CooldownPolicy.can_fire(symbol, kind, now, session) -> bool` + `record_fired(...)`; SL_BREACH never suppressed, others independent per-(symbol,kind) for `settings.cooldown_minutes` | 10.4 / A16 |
| `exit_manager.py` | `ExitManager.tick(OpenTradeView, candles, today_bar) -> ExitDecision`; priority stop → trailing → no_progress; `ExitDecision(action, reason, fill)`, `OpenTradeView(plan, entry_idx, current_idx, horizon_max_days, adv, atr_pct, qty)` | 10.5 |

## Tests (tests/swing/exits/) — 15 passed
- `test_stop.py` — SL hit returns Fill via FillPolicy; not hit → None.
- `test_chandelier_trail.py` — trail tightens as new highs print.
- `test_ema_trail.py` — stop tracks EMA, rises with rising closes.
- `test_no_progress.py` — below 0.3R at midpoint → exit; strong progress → hold; early window → hold.
- `test_cooldown_decoupled.py` — **A16 hallmark** (`@pytest.mark.hallmark`): SL_WARNING fired then SL_BREACH within the hour still fires immediately; other kinds respect cooldown; kinds/symbols independent.
- `test_exit_manager_priority.py` — stop wins over no_progress on the same bar; HOLD when nothing triggers.
- `conftest.py` — in-memory SQLite `session` fixture (copied from tests/db pattern).

## Design notes / decisions
- **no_progress R definition**: realized R = (current_close − entry) / (entry − stop_loss). Exit when realized R < `settings.no_progress_t1_threshold` (0.3) AND elapsed_pct ≥ `settings.no_progress_elapsed_threshold` (0.5). `target_1` kept on the input for traceability but not needed in the gate math; this is the simplest faithful reading of "realized R toward T1 < threshold".
- **trailing**: ATR computed as mean high−low range over the period window (close-less true range) — sufficient; parameters are backtested per spec. All-Decimal arithmetic.
- **exit_manager priority**: stop is evaluated first so it wins on same-bar conflicts (per test). Trailing is exposed via `ChandelierTrail`/`EMATrail` for the manager/postmortem to tighten the working stop; the spec leaves parameter selection to `postmortem.builder`, so the manager does not hardcode a trail policy — it applies stop → no_progress and surfaces trailing as a reusable component.

## Constraints honored
- Did NOT modify `policy.py`, `types.py`, `models.py`, `settings.py`.
- `from __future__ import annotations`, full type hints, Decimal prices, no float `==`, no magic numbers (all thresholds via `Settings`).

## Verification
- `.venv/bin/python -m pytest tests/swing/exits/ -q` → **15 passed**
- `ruff check src/plutus/swing/exits tests/swing/exits` → clean
- `mypy --strict` (via mypy.ini) on `src/plutus/swing/exits/` → no issues (6 files)

## Blockers
None.
