# PRD — Plutus v2

> Product requirements. The bible is `docs/PLUTUS_CONSOLIDATED_REVIEW.md`. This document re-states scope, sequencing, and the action-item trace into specs.

---

## 1. Product summary

Plutus v2 is a single-operator NSE trading system with two domains:

- **Swing** — day-to-week trades. Bundle-based entries. Expectancy-gated. Three-baseline benchmarked. Exit-aware.
- **Accumulation** — multi-month tranche-based positions. Fundamentals + RS-blend. Thesis-invalidated exits. Bull-ready voluntary conversion to swing.

The system is run by one operator, alerts via Telegram, observed via a Streamlit dashboard, and gated against real money by §15 of `15_go_live_bar.md`.

The system does **not** auto-execute on a broker. It produces alerts; the operator places trades and logs real fills back into the system for calibration honesty (B10).

---

## 2. Goals

1. **Make every backtest number mean what it says.** Costs, fill realism, expectancy gating, benchmarks.
2. **Make the human-judgment contract real.** Pillar decomposition + counterfactuals + calibration CIs + the soft dead-zone equip the operator's final 10%.
3. **Prevent over-confidence.** SPRT, multiple-testing correction, regime-conditioned calibration, auto-tune off by default.
4. **Two domains, two rhythms, no force-migration.** Swing and accumulation share `shared/` but never `swing/` ↔ `accumulation/` imports.

---

## 3. Non-goals

- Multi-user / multi-tenant.
- Broker integration / auto-execution.
- Options or F&O strategies (F&O metadata used only as risk inputs).
- Intra-day signals shorter than 1 day.
- US/global markets.

---

## 4. Domains and modules at a glance

```
shared/                           swing/                       accumulation/
├── cost_model/      (B1)         ├── bundles/                 ├── fundamentals/  (A12)
├── fills/           (A1)         │   ├── trend                ├── rs/            (A12)
├── regime/          (A7, B13)    │   ├── breakout (B7)        ├── tranches/      (A13)
├── risk/            (B3-B5)      │   ├── reversal             ├── exits/         (B9)
│   ├── heat                      │   ├── vcp                  ├── bull_ready/
│   ├── sector_cap                │   ├── composite (A5)       ├── scoring/
│   ├── correlation_guard         │   ├── pead     (C2)        └── postmortem/
│   ├── adv_cap                   │   └── smc      (C3)
│   ├── drawdown_governor         ├── scoring/     (A2, A3, A4, A10)
│   ├── cash_position (B15)       ├── entries/     (A9, A15, B6, B7)
│   └── allocation    (B16)       ├── exits/       (B8, A16)
├── universe/        (A17)        ├── sizing/      (A6)
├── calibration/     (A14, B17)   ├── sentiment/   (A8)
├── benchmarks/      (B2)         └── postmortem/
└── smart_money/     (A7, A9)
```

---

## 5. Action-item trace (every item from PART 4 of the bible)

### CHANGE (A)
| # | Item | Spec doc | Test hallmark |
|---|---|---|---|
| A1 | Backtest fills realism | 05 | `test_fill_policy_stop_gap.py` |
| A2 | Pooled OOS per-regime shrunk Sharpe selection | 07, 10 | `test_selector_ranks_by_oos_per_regime_shrunk_sharpe.py` |
| A3 | Break circularity (Technical pillar no per-stock Sharpe) | 07, 10 | `test_pillars_no_per_stock_sharpe_leak.py` |
| A4 | Expectancy gate | 07 | `test_expectancy_primary_gate.py` |
| A5 | Composite geometry | 07 | `test_composite_a5_hallmark.py` |
| A6 | 2% vs 5% resolved | 02, 07 | `test_size_only_one_risk_constant.py` |
| A7 | Smart Money restructure / FII-DII relocated | 06, 09 | `test_no_fii_dii_in_per_stock.py` |
| A8 | Sentiment 5% + corroborated kill + deterministic-only | 09 | `test_corroboration_*.py` + `test_color_is_color_only.py` |
| A9 | Delivery-adjusted volume gate | 04, 07, 09 | `test_volume_gate.py` |
| A10 | Technical de-correlation | 07 | `test_pillars_technical.py` |
| A11 | Default plan from Composite | 07 | `test_selector_default_composite_seed.py` |
| A12 | Accumulation fundamentals fix | 08 | `test_valuation_cap.py`, `test_valuation_growth_uses_cagr_not_yoy.py` |
| A13 | ATR-normalized tranche triggers + thesis re-check | 08 | `test_triggers.py`, `test_revalidation.py` |
| A14 | Tuning loop fix | 11 | `test_tuner_objective_is_expectancy.py` |
| A15 | Monday re-validation | 07, 13 | `test_jobs_monday_revalidation.py` |
| A16 | Cooldowns decoupled | 07, 13 | `test_monitor_sl_breach_always_fires.py` |
| A17 | PIT universe in ₹ | 04 | `test_universe_pit.py` |

### ADD (B)
| # | Item | Spec doc | Test hallmark |
|---|---|---|---|
| B1 | Cost & slippage model | 05 | `test_costs.py`, `test_slippage.py` |
| B2 | Three benchmarks | 10, 14 | `test_postmortem_three_benchmarks.py` |
| B3 | Correlation-aware portfolio heat | 06 | `test_portfolio_heat.py`, `test_correlation_guard.py` |
| B4 | Drawdown governor | 06 | `test_drawdown_governor.py` |
| B5 | ADV cap | 06 | `test_adv_cap.py` |
| B6 | Earnings blackout | 04, 07 | `test_earnings_gate.py` |
| B7 | Circuit awareness | 07 | `test_circuit_gate.py` |
| B8 | Exit layer (trailing + no-progress) | 07 | `test_chandelier_trail.py`, `test_no_progress.py` |
| B9 | Accumulation thesis-invalidation exit | 08 | `test_thesis_invalidation.py` |
| B10 | Mock-vs-real fill logging | 05, 12, 14 | `test_mock_vs_real.py`, `test_real_fill_preference.py` |
| B11 | Freshness assertion | 04, 13 | `test_freshness.py`, `test_jobs_freshness_aborts.py` |
| B12 | Reconciliation | 04 | `test_ohlcv_reconciliation.py` |
| B13 | Regime detector inputs | 04, 06 | `test_breadth.py`, `test_vix.py` |
| B14 | Per-regime bundle stat store | 03, 10 | `test_per_regime_store.py` |
| B15 | Cash-as-position | 06, 14 | `test_cash_position.py` |
| B16 | Bounded regime-adaptive allocation | 06 | `test_allocation.py` |
| B17 | Dashboard honesty (pillars, counterfactual, badges, dead-zone) | 14 | `test_signals_dead_zone_shows_buy_watch.py` |
| B18 | Midweek mini-screen | 13 | `test_jobs_midweek_gated_off.py` |

### REMOVE / GATE (C)
| # | Item | Spec doc | Test hallmark |
|---|---|---|---|
| C1 | Raw FII/DII out of per-stock | 09 | `test_no_fii_dii_in_per_stock.py` |
| C2 | PEAD gated | 07 | `test_pead.py` |
| C3 | SMC gated | 07, 14 | `test_strategy_lab_smc_display_only.py` |
| C4 | Raw-volume confirmation removed | 07 | `test_volume_gate.py` |
| C5 | Win rate not headline | 11, 14 | `test_postmortem_no_naked_win_rate.py` |
| C6 | "No LLM leak" claim made true | 09 | `test_color_is_color_only.py` |

### IMPROVISE (D) — themes, not items
| # | Theme | Anchored in |
|---|---|---|
| D1 | Exit-quality investment over entry-count | 07 (B8), 11 |
| D2 | Honest edge framing | 15 |
| D3 | Calibration as inference with uncertainty | 11 |
| D4 | Human-judgment contract via dashboard | 14 |

### OPTIMIZE (E) — post-P0/P1
| # | Item | Spec doc | Phase |
|---|---|---|---|
| E1 | Per-regime target multiples | 07, 11 | P3 |
| E2 | Beta-adjusted swing sizing | 07 | P3 |
| E3 | MFE/MAE-driven re-derivation | 07 | P3 |
| E4 | F&O OI build-up signal | 09 | P3 |
| E5 | RS weight increase | 08 | P3 |

---

## 6. Sequencing

**Phase 1 (P0)** — bring backtest numbers to meaning:
B1 → A1 → A2/A3 → A4 → A5 → B2.
Spec docs: 05, 06 (cost-side), 07 (selector + expectancy + composite), 10.

**Phase 2 (P1)** — risk, signals, data, exits, tuning, alerts:
A6, B3, B4, B5, A7, A8, A9, A10, A11, B6, B7, B8, A14, A16, A17, B12.
Spec docs: 02, 04, 06, 07, 09, 11, 13.

**Phase 3 (P2/P3)** — accumulation polish, regime upgrades, dashboard honesty, allocation breathing, gated pruning, optimizations:
A12, A13, A15, B9, B10, B11, B13, B14, B15, B17, B18, C2 evidence, C3 evidence, E1–E5.
Spec docs: 04, 08, 13, 14.

**Go-live gate** — `15_go_live_bar.md`. Two quarters paper, ≥1 regime flip, beats both baselines net of costs.

---

## 7. Reading order for the build agent

1. `00_principles.md` — binding rules.
2. `TESTING.md` — how to test.
3. `01_folder_structure.md` — build the tree.
4. `02_environments_config.md` — settings.
5. `03_database.md` — models.
6. `04_data_pipeline.md` — adapters.
7. `05_cost_and_fill_model.md` — P0 anchor.
8. `06_shared_regime_and_risk.md`
9. `07_swing_domain.md` — biggest.
10. `08_accumulation_domain.md`
11. `09_sentiment_and_smart_money.md`
12. `10_backtesting_and_benchmarks.md`
13. `11_calibration_and_tuning.md`
14. `12_api_layer.md`
15. `13_alerts_and_scheduler.md`
16. `14_dashboard.md`
17. `15_go_live_bar.md`
18. `GLOSSARY.md` — reference, read as needed.

Work top-down within each doc, TDD-first.

---

## 8. Definition of project done

- All hallmark tests green.
- `mypy --strict`, `ruff`, `import-linter` green.
- Coverage ≥ 90% on `swing/`, `accumulation/`, `shared/`.
- Old `src/plutus/` (v1) deleted per `01_folder_structure.md` §3.
- Phase 1, Phase 2, Phase 3 acceptance checklists all checked in PR descriptions.
- Paper trading window started and recorded.

---

## 9. Risks not in scope

- Provider outages handled per `04_data_pipeline.md` (fallback chain + freshness assertion); deeper redundancy is out of scope.
- Telegram outage tolerated; WhatsApp optional fallback.
- Hardware/OS failure: deployment doc in `deployment/` handles backups (out of spec, in ops).
