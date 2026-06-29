# Phase 2 Technical Documentation — Index

## Overview

Phase 2 transforms the Plutus dashboard from a structurally correct but unusable tool into a reliable, efficient trading workflow. It consists of 4 sub-phases with 15 features total.

**Development Methodology:** Test-Driven Development (TDD)
- Write failing tests FIRST based on acceptance criteria
- Implement minimal code to make tests pass
- Refactor while keeping tests green

**Stack:** Streamlit + FastAPI + PostgreSQL + LangGraph (unchanged from Phase 1)

## Phase Documents

| Phase | File | Theme | Features | Duration |
|-------|------|-------|----------|----------|
| 2A | [PHASE_2A.md](./PHASE_2A.md) | Fix What's Broken | F1–F4 (P0) | 3–4 days |
| 2B | [PHASE_2B.md](./PHASE_2B.md) | Close the Dashboard Gaps | F5–F8 (P1) | 5–7 days |
| 2C | [PHASE_2C.md](./PHASE_2C.md) | Workflow Efficiency | F9–F11 (P1/P2) | 7–10 days |
| 2D | [PHASE_2D.md](./PHASE_2D.md) | Trader Power Features | F12–F15 (P2) | 10–14 days |

## Dependency Chain

```
Phase 2A (no deps) → Phase 2B (depends on 2A) → Phase 2C (depends on 2B) → Phase 2D (depends on 2C)
```

## Parallel Task Convention

Within each phase document, independent tasks are marked with:

```
## 🔀 PARALLEL TASK GROUP: <group-name>
```

Tasks within a parallel group can be assigned to separate child agents / workers without conflict. Cross-group dependencies are explicitly listed.

## File Ownership Rules (for parallel execution)

| File / Module | Owner (if contested) |
|---------------|---------------------|
| `src/dashboard.py` | Single owner per phase — split into helper modules first |
| `src/plutus/backtesting/runner.py` | F1 only |
| `src/plutus/api/routes.py` | F4 (new endpoint), then F5 (paper-trade endpoint) |
| `src/plutus/data/ohlcv.py` | F1 only |
| `src/plutus/data/universe.py` | F7 only |
| `tests/` | Each feature owns its own test file — no conflict |

## Test Infrastructure

- **Framework:** pytest (already configured)
- **Mocking:** pytest-mock + unittest.mock
- **API Testing:** httpx.AsyncClient (FastAPI TestClient)
- **Dashboard Testing:** Streamlit AppTest (st.testing)
- **Naming:** `tests/test_phase2_{feature_id}.py` (e.g., `tests/test_phase2_f1_backtest.py`)

## Success Metrics (Phase-Level)

| Metric | Target |
|--------|--------|
| Time from dashboard open → first actionable signal | < 30s (cached) |
| Time from signal → paper trade logged | < 3 min (no Telegram) |
| Backtest Sharpe on RELIANCE (Trend, 90d) | -2 to +3 range |
| Analyze pipeline user feedback | < 2s of button click |
| Hard crashes / blank tabs | 0 unhandled exceptions |
| PRD features implemented and visible | > 90% |
