# 01 — Folder Structure

> Greenfield rebuild. Build the new tree from scratch under `src/plutus/`. Port logic from the old tree behind tests. When the new tree is green end-to-end, delete the old artifacts listed in §3.

---

## 1. Repository layout (final state)

```
plutus-app/
├── .env                         # SINGLE source of truth (was duplicated in src/.env)
├── .env.example                 # documented defaults, committed
├── .venv/                       # repo root (was src/.venv)
├── .gitignore                   # ignores .venv, logs/, reports/, cache/, *.pyc, __pycache__
├── pyproject.toml               # NEW — replaces ad-hoc requirements.txt
├── pytest.ini                   # repo root, one only
├── README.md
├── ruff.toml
├── mypy.ini
├── importlinter.ini             # enforces §3 of 00_principles.md
│
├── docs/                        # PLUTUS_CONSOLIDATED_REVIEW.md (the bible)
├── specs/v2/                    # this directory
├── migrations/                  # alembic
├── logs/                        # runtime, gitignored
├── reports/                     # runtime weekly/postmortem reports, gitignored
├── cache/                       # runtime data cache, gitignored
├── screenshots/                 # dashboard regression screenshots
├── deployment/                  # docker / systemd / k8s
├── scripts/                     # one-off CLIs (refresh universe, replay backtest)
│
├── src/
│   └── plutus/                  # ONLY package — no src/src
│       ├── __init__.py
│       ├── config/
│       │   ├── __init__.py
│       │   ├── settings.py      # Pydantic Settings
│       │   └── logging.py       # logger factory
│       │
│       ├── data/                # provider adapters; no domain logic
│       │   ├── ohlcv.py
│       │   ├── delivery.py
│       │   ├── fii_dii.py
│       │   ├── vix.py
│       │   ├── breadth.py
│       │   ├── bulk_block.py
│       │   ├── earnings_calendar.py
│       │   ├── news.py
│       │   ├── trading_calendar.py
│       │   ├── universe.py
│       │   └── reconciliation.py
│       │
│       ├── db/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── session.py
│       │   └── init_db.py
│       │
│       ├── shared/
│       │   ├── cost_model/      # B1
│       │   ├── fills/           # A1
│       │   ├── regime/          # index + FII/DII + breadth + VIX
│       │   ├── risk/            # heat, sector cap, corr guard, ADV cap, DD governor
│       │   ├── universe/        # PIT, ₹-median liquidity
│       │   ├── calibration/     # SPRT, CIs, regime-conditioned (A14)
│       │   ├── benchmarks/      # 3 baselines (B2)
│       │   └── smart_money/     # delivery, bulk_block, mf_accumulation
│       │
│       ├── swing/
│       │   ├── __init__.py
│       │   ├── bundles/
│       │   │   ├── base.py
│       │   │   ├── trend.py
│       │   │   ├── breakout.py
│       │   │   ├── reversal.py
│       │   │   ├── vcp.py
│       │   │   ├── composite.py     # A5 geometry fix
│       │   │   ├── pead.py          # C2 — gated
│       │   │   └── smc.py           # C3 — gated
│       │   ├── scoring/             # pillars, expectancy gate (A4)
│       │   ├── entries/             # Monday re-validation (A15)
│       │   ├── exits/               # trailing, no-progress, SL (B8, A16)
│       │   ├── sizing/              # ADV cap, risk per trade (A6)
│       │   ├── postmortem/
│       │   └── sentiment/           # corroborated hard-kill (A8)
│       │
│       ├── accumulation/
│       │   ├── __init__.py
│       │   ├── fundamentals/        # multi-year CAGR, valuation cap (A12)
│       │   ├── rs/                  # 30/90/180 blend
│       │   ├── tranches/            # ATR-normalized triggers + thesis re-check (A13)
│       │   ├── exits/               # thesis-invalidation (B9)
│       │   └── bull_ready/          # voluntary conversion
│       │
│       ├── backtesting/             # pooled, walk-forward OOS, per-regime
│       ├── scheduler/               # Sun full, Mon 09:10, midweek mini, daily exit
│       ├── alerts/                  # telegram primary, whatsapp optional
│       ├── api/                     # FastAPI, split by domain
│       │   ├── shared.py
│       │   ├── swing.py
│       │   └── accumulation.py
│       ├── dashboard/               # streamlit
│       │   ├── app.py               # entry point
│       │   ├── windows/             # one file per sidebar item
│       │   │   ├── home.py
│       │   │   ├── user_flow.py
│       │   │   ├── signals.py
│       │   │   ├── positions.py
│       │   │   ├── candidates.py
│       │   │   ├── tranches.py
│       │   │   ├── settings.py
│       │   │   ├── postmortem.py
│       │   │   ├── calibration.py
│       │   │   └── strategy_lab.py
│       │   └── components/          # reusable widgets
│       │       ├── pillar_bar.py
│       │       ├── calibration_badge.py
│       │       ├── counterfactual.py
│       │       ├── regime_banner.py
│       │       └── tranche_pills.py
│       └── llm/                     # openrouter client; outputs are color-only
│
└── tests/                       # mirrors src/plutus/ exactly
    ├── conftest.py
    ├── fixtures/                # parquet OHLCV, JSON FII/DII, etc.
    ├── config/
    ├── data/
    ├── db/
    ├── shared/
    ├── swing/
    ├── accumulation/
    ├── backtesting/
    ├── scheduler/
    ├── alerts/
    ├── api/
    ├── dashboard/
    └── llm/
```

---

## 2. Test tree mirror rule (binding)

For every file `src/plutus/X/Y.py` there is a file `tests/X/test_Y.py`. No test in the wrong place. CI enforces with a small script (`scripts/check_test_mirror.py`).

Exceptions:
- `__init__.py` files don't get a test.
- `base.py` (abstract bases) gets a test that subclasses can't bypass the abstract contract.

---

## 3. Delete list (execute at the end of Phase 1)

These are confirmed obsolete. Do NOT delete before the new tree compiles green; some have data worth re-reading first.

| Path | Reason |
|---|---|
| `src/src/` | Stray nested duplicate (cache + 3 stale weekly reports). Verify nothing in `src/src/reports/` is newer than `src/reports/` and delete. |
| `src/dashboard.py` | Duplicate entry point; replaced by `src/plutus/dashboard/app.py`. |
| `src/.env` | Duplicate; only repo-root `.env` survives. |
| `src/.venv/` | Move venv to repo root; delete in-src venv. |
| `src/__pycache__/`, all nested `__pycache__/` | Build artifact; add to `.gitignore`. |
| Repo-root `main.py` | If functionality is needed, move to `scripts/`. Otherwise delete. |
| Repo-root `test_buttons_interactive.py`, `test_dashboard_comprehensive.py`, `test_dashboard_e2e.py`, `test_final.py`, `test_functional.py` | Replaced by `tests/dashboard/*` Playwright tests. Read each for any unique coverage idea, then delete. |
| `specs/overhaul/`, `specs/phase2/`, `specs/v2_old/`, repo-level `specs/01_sequencing.md` through `specs/15_deployment.md`, `specs/PRD.md`, `specs/PRD_PHASE2.md`, `specs/_CHANGE_SPEC.md`, `specs/first-i-want-u-velvety-tide.md` | Superseded by `specs/v2/`. |
| `docs/PM_REVIEW.md`, `docs/PLUTUS_REVIEW.md`, `docs/PLUTUS_ENGINE_REVIEW.md` | The consolidated review (`PLUTUS_CONSOLIDATED_REVIEW.md`) absorbs these. Keep `PLUTUS_ENGINE.md` (reference) and the consolidated review only. |
| `docs/FINAL_SUMMARY.md`, `docs/TEST_REPORT.md`, `docs/YFINANCE_ISSUES.md`, `docs/DASHBOARD_USER_GUIDE.md`, `docs/LOCAL_TESTING.md`, `docs/dashboard_test.png`, `docs/local-stop.sh`, `docs/local-test.sh` | Stale operational notes; replaced by `specs/v2/13_alerts_and_scheduler.md` and `deployment/`. |
| `src/scripts/` | Move to repo-root `scripts/`. |
| `src/reports/`, `src/logs/`, `src/plutus/data/.cache/` | Move runtime dirs out of `src/`. |

---

## 4. Order of operations (so nothing is lost mid-rebuild)

1. Create `src/plutus/` skeleton (empty packages with `__init__.py`).
2. Move `.venv` to repo root; recreate if simpler.
3. Move `.env` to repo root; reconcile with `src/.env`.
4. Write `pyproject.toml`; pin Python version (`3.11+`).
5. Walk the test tree in the order of the docs (start with `tests/shared/cost_model/`).
6. Implement each module against its failing test (per `00_principles.md` §2).
7. When end-to-end Phase 1 (P0 items) is green, run the delete list.
8. When Phase 2 (P1) is green, delete `src/plutus/` legacy modules that v2 has fully replaced.
9. Final state: only `src/plutus/` (v2) exists.

---

## 5. Runtime directories (gitignored)

- `logs/YYYY-MM-DD/app.log` — daily rolled, structured JSON-line entries.
- `reports/weekly/YYYY-MM-DD.md` — Sunday postmortem.
- `cache/ohlcv/<symbol>_<lookback>.parquet` — provider responses, TTL by `02_environments_config.md`.
- `cache/regime/<date>.json` — daily regime snapshot.

Code never writes to `src/`. Tests never write outside `tmp_path` fixtures.

---

## Acceptance criteria

- [ ] `tree -L 3 src/plutus/` matches §1.
- [ ] `tree -L 3 tests/` mirrors `src/plutus/` (verified by `scripts/check_test_mirror.py`).
- [ ] `find . -name __pycache__ -prune -o -name .venv -prune -o -name "*.py" -print | grep -c "src/src"` == 0.
- [ ] No `.env` exists outside repo root.
- [ ] CI runs `import-linter` and the test-mirror check.
- [ ] Delete list executed; `git status` clean after.
