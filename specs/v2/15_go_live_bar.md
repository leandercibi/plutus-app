# 15 — Go-Live Bar

> The minimum evidence before a rupee of real capital deploys. Both reviewers converge on this; non-negotiable. Source: consolidated review PART 5.

---

## 1. The bar (verbatim)

> Paper-trade a minimum of **two full quarters spanning at least one regime flip**, with the cost model on and real fills logged, watching WRONG_DIRECTION counts and bucket calibration with CIs — and the system must beat **both** the regime-baseline and the random-selection baseline net of costs before a rupee of real size goes on.

> If it only beats buy-and-hold but not the regime baseline, the stock-picking layer isn't earning its complexity and the honest product is a regime-switched index strategy with an accumulation sleeve.

---

## 2. Quantitative gates

All gates must be green simultaneously for the same closed-out test window.

| Gate | Condition |
|---|---|
| G1 — Duration | ≥ 2 full calendar quarters of paper trading. |
| G2 — Regime coverage | The window contains ≥ 1 confirmed regime flip (BULL↔BEAR or BULL↔SIDEWAYS), as recorded by `RegimeFlipDetector`. |
| G3 — Beats Nifty B&H | Plutus swing net return > Nifty buy-and-hold net return. |
| G4 — Beats regime-switched baseline | Plutus net > regime-switched baseline net by ≥ 1.5pp. |
| G5 — Beats random-liquid baseline | Plutus net > random-liquid baseline net by ≥ 2pp. |
| G6 — Calibration honest | For ≥ 80% of (bucket, regime) cells with n ≥ 20, realized expectancy CI overlaps forecast expectancy CI. |
| G7 — Costs realistic | Mock-vs-real slippage divergence p90 ≤ 15 bps on closed trades that have both fills logged. |
| G8 — No A/B/C P0/P1 regression | All hallmark tests still green (A1, A3, A4, A5, A6, A14, A15, A16, B2). |
| G9 — Cooldowns and freshness clean | Zero recorded SL_BREACH suppressed by a warning cooldown. Zero stale-candle alert ignored. |
| G10 — Drawdown governed | Max realized drawdown from pool high-water mark < 12%; governor triggered on schedule when ≥ 7%. |

If G3 passes but G4 or G5 fails, the honest product is the **regime-switched index strategy + accumulation sleeve** — ship that, not the swing stock-picker.

---

## 3. Operational gates

| Gate | Condition |
|---|---|
| O1 — Real fills logged | ≥ 30% of paper trades have at least one user-logged REAL fill (proves the calibration path is exercised). |
| O2 — Postmortems published | Every weekly postmortem produced and reviewed; no missed weeks. |
| O3 — Tuner usage | At most 2 manually-applied tuner proposals across the window (over-tuning is failure). |
| O4 — Universe stability | Universe-size variance per snapshot < 10%; sudden contractions investigated. |
| O5 — Provider reconciliation | All run-level reconciliation reports clean or explained. |

---

## 4. Honest-edge framing

The dashboard's User Flow window prominently displays which edge has been earned:

- **No edge proven** — pre-G3.
- **Beta edge** — G3 only. "System captures Nifty beta with extra steps. Honest answer: hold Nifty."
- **Regime edge** — G3 + G4 (G5 fails). "System's value is timing. Ship regime-switched index + accumulation."
- **Stock-picking edge** — G3 + G4 + G5. "System earns its complexity. Live trading authorized at the configured risk." This is the only state that unlocks the "Go Live" button.

The button is gated server-side in the API (`/admin/go-live`) by the same conditions.

---

## 5. Process

1. Phase 1 (P0 items) merged green. Backtest reruns clean.
2. Paper-trading window opens. All alerts active; trades logged but unsized in production accounts. Operator logs every real broker fill they would have made.
3. Weekly postmortem reviewed. Calibration CI table inspected for any (bucket, regime) where realized is decisively outside the forecast CI — those buckets are flagged for re-examination, not auto-tuned (A14).
4. End of Q2 review meeting: are G1–G10 + O1–O5 green?
   - Yes → Go-Live button enabled. Initial real-money sizing at 25% of intended risk; scale to 100% over 4 weeks if no regression.
   - No → Identify which gate fails. If structural (G4 or G5 fail), pivot to the honest-edge product. If operational (Oi), continue paper.

---

## 6. Tests (`tests/go_live/`)

| Test file | Cases |
|---|---|
| `test_gate_evaluator.py` | All ten quantitative gates computed from a synthetic 6-month window. |
| `test_gate_operational.py` | Operational gates computed from run-log fixtures. |
| `test_honest_edge_label.py` | Each combination of G3/G4/G5 produces the correct label string. |
| `test_go_live_button_gated.py` | API endpoint returns 403 unless all gates green. |
| `test_go_live_button_pure_function.py` | Gate evaluator is deterministic; no time-of-day side effects. |
| `test_pivot_product_path.py` | G3 green + G4 fail → operator sees regime-switched product recommendation explicitly. |

---

## Acceptance criteria

- [ ] Gate evaluator deterministic, tested.
- [ ] Dashboard surfaces the four edge states honestly.
- [ ] `/admin/go-live` server-side gated.
- [ ] Process §5 documented in `docs/` for the operator (separate from spec).
