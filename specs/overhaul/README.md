# Plutus Overhaul — Phase Documentation Index

Agent-readable, test-driven technical specs derived from the approved plan at
`/Users/leander/.claude/plans/first-the-scale-you-hazy-naur.md`.

## How to use these docs (for agents)

Each phase doc is self-contained. To execute a phase:

1. Read the phase metadata block at the top. Confirm prerequisites (other phases) are `done`.
2. Walk the task list **in declared order**. For each task, check `parallelizable: yes|no`.
   - If `parallelizable: yes`, the task names a **parallel group**. Tasks sharing a group can be dispatched to subagents in the same message.
   - If `parallelizable: no`, the task is a sequential pin. Complete it (and verify its tests) before moving to the next group.
3. **TDD is mandatory.** Every task lists a `Test first` block — write the failing test before touching production code. Then make it pass. Then verify with the green-bar command.
4. After each task, update its status in this README (or the phase-level Done checklist).

## Conventions

- **Task IDs**: `TASK-<phase>.<seq>` (e.g., `TASK-0.2`). Stable; referenced from other phase docs.
- **Code refs**: `path:line` format. Lines refer to current HEAD; re-verify after merges.
- **Parallel groups**: Identified by a label like `parallel-group: 1A`. Tasks in the same group are independent and safe to dispatch in one batch.
- **Streamlit tests**: All UI changes use `streamlit.testing.v1.AppTest` per the [Streamlit testing reference](https://docs.streamlit.io/develop/api-reference/app-testing).
- **Verification**: Each phase ends with a `Verification` section. A phase is **only** done when every verification box is ticked.

## Phase dependency graph

```
Phase 0  (F1 fix) ──┬──► Phase 1  (Scoring rubric) ──┬──► Phase 2  (Bundle hardening) ──► Phase 5  (VCP + PEAD)
                    │                                │
                    └──► Phase 4a (Outcome tracker) ─┼──► Phase 4b (Walk-forward) ──► Phase 4c (Calibration)
                                                    │
                                                    └──► Phase 4.5 (Self-finetuning loop, lags 30d)

Phase 3a (Regime data) ──► (feeds Phase 1 Regime pillar, Phase 2 regime gate)
Phase 3b (Tickertape)  ──► (feeds Phase 1 SmartMoney pillar, Phase 3a sector mapping)

Phase 6  (Editable params) ──► touches Phase 1 thresholds + Phase 7 portfolio
Phase 7  (Mock portfolio + Analyze card) ──► consumes Phase 1 sub-scores, Phase 4a outcomes
Phase 8a (Alerts)           ──► consumes Phase 7 open positions

Dashboard surfacing pass    ──► consumes everything; runs last.
```

## Phase index

| ID | Title | File | Status | Depends on |
|---|---|---|---|---|
| 0 | F1 backtest data validation | [phase_0_f1_fix.md](phase_0_f1_fix.md) | pending | — |
| 1 | Deterministic scoring rubric | [phase_1_scoring.md](phase_1_scoring.md) | pending | 0, 3a |
| 2 | Per-bundle hardening (5 bundles) | [phase_2_bundles.md](phase_2_bundles.md) | pending | 0, 3a |
| 3a | Nifty regime + sector index data | [phase_3a_regime.md](phase_3a_regime.md) | pending | — |
| 3b | Tickertape scraper (MF / sector / beta) | [phase_3b_tickertape.md](phase_3b_tickertape.md) | pending | — |
| 4a | Outcome tracker | [phase_4a_outcomes.md](phase_4a_outcomes.md) | pending | 0 |
| 4b | Walk-forward harness | [phase_4b_walkforward.md](phase_4b_walkforward.md) | pending | 0, 4a |
| 4c | Score calibration | [phase_4c_calibration.md](phase_4c_calibration.md) | pending | 4a (≥30 closed trades) |
| 4.5 | Self-finetuning loop | [phase_4_5_self_tune.md](phase_4_5_self_tune.md) | pending | 4a (≥30 trades), 4c |
| 5 | VCP + PEAD strategies | [phase_5_vcp_pead.md](phase_5_vcp_pead.md) | pending | 2, 3b |
| 6 | Editable trading parameters | [phase_6_editable_params.md](phase_6_editable_params.md) | pending | — |
| 7 | Mock portfolio + analyze card | [phase_7_portfolio_analyze.md](phase_7_portfolio_analyze.md) | pending | 1, 4a |
| 8a | Position-aware alerts (Telegram) | [phase_8_alerts.md](phase_8_alerts.md) | pending | 7 |
| Dash | Dashboard surfacing pass | [phase_dashboard.md](phase_dashboard.md) | pending | 1, 3a, 4a, 7 |

## Test runner conventions

- **Python tests**: `pytest tests/` from repo root. New tests live under `tests/` mirroring the source tree.
- **Streamlit tests**: New file `tests/dashboard/test_<component>.py` per UI surface. Use `AppTest.from_file()` for full-page tests or `AppTest.from_function()` for component tests.
- **Integration**: `tests/integration/` for cross-module flows (e.g., scoring → synthesizer → DB write).
- **Fixtures**: shared OHLCV fixtures live in `tests/conftest.py`. Five-symbol fixture (`RELIANCE, HDFCBANK, BHARTIARTL, INFY, TATAMOTORS`) is the verification baseline.

## Template

When adding a new phase doc, copy [_template.md](_template.md) and replace placeholders.
