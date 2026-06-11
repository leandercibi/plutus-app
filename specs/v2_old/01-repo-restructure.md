# 01 — Repo restructure + dead code removal

## Why

The current layout has three independent problems:

1. **Accidental nesting.** `src/src/plutus/data/.cache/` was created by code running from the wrong cwd. The cache holds 500+ OHLCV pickle files. The directory should not exist.
2. **Output dirs inside the package.** `src/logs/`, `src/reports/`, `src/plutus/...` mixes generated output with source code. CI cannot reliably know what to ignore.
3. **Layer-by-layer module split.** `src/plutus/agents/`, `src/plutus/strategies/`, `src/plutus/backtesting/` group code by technical layer. We are adding a second domain (accumulation); a layer split forces every domain change to touch every layer folder. We will split by domain.

## The target layout

```
plutus-app/                              ← project root
├── .env                                 ← keep
├── .env.example                         ← NEW (commit; .env stays gitignored)
├── .gitignore                           ← update
├── README.md                            ← keep, update install + run sections
├── pyproject.toml                       ← NEW (PEP 621 + setuptools)
├── pytest.ini                           ← keep, update testpaths
├── main.py                              ← keep at root (entry point)
│
├── src/
│   └── plutus/
│       ├── __init__.py
│       │
│       ├── core/                        ← shared cross-domain infrastructure
│       │   ├── __init__.py
│       │   ├── config.py                ← from src/plutus/config.py
│       │   ├── config_params.py         ← from src/plutus/config_params.py
│       │   ├── logging.py               ← NEW (extract from main.py)
│       │   ├── llm/
│       │   │   ├── __init__.py
│       │   │   └── openrouter_client.py ← from src/plutus/agents/openrouter_client.py
│       │   ├── db/
│       │   │   ├── __init__.py
│       │   │   ├── base.py              ← SessionLocal, Base, init_db (from db/models.py top)
│       │   │   ├── models/
│       │   │   │   ├── __init__.py      ← re-exports (back-compat for imports)
│       │   │   │   ├── shared.py        ← WeeklyRun, TradingParam, MockPortfolio, PaperTrade, Alert, MarketRegimeSnapshot
│       │   │   │   ├── swing.py         ← Recommendation, RejectedHeadline (existing swing-only rows)
│       │   │   │   └── accumulation.py  ← NEW: AccumulationRun, AccumulationCandidate, AccumulationPosition, AccumulationTranche
│       │   │   └── migrations/          ← from project root /migrations/
│       │   ├── data/                    ← shared market data
│       │   │   ├── __init__.py
│       │   │   ├── ohlcv.py             ← AngelOne block stays byte-identical
│       │   │   ├── universe.py
│       │   │   ├── regime.py
│       │   │   ├── smart_money.py
│       │   │   ├── news.py
│       │   │   ├── tickertape.py
│       │   │   ├── fundamentals.py      ← NEW (yfinance wrapper, see 04)
│       │   │   ├── trading_calendar.py
│       │   │   ├── refresh_universe.py
│       │   │   └── seeds/
│       │   │       ├── seed_universe.csv
│       │   │       ├── seed_universe_v2.csv
│       │   │       └── nifty100_accumulation.csv     ← NEW (see 04)
│       │   ├── alerts/
│       │   │   ├── __init__.py
│       │   │   ├── channels.py          ← TelegramChannel, WhatsAppChannel (stub)
│       │   │   └── monitor.py           ← shared monitor loop; per-domain trigger fns live in domain modules
│       │   └── utils/
│       │       └── __init__.py
│       │
│       ├── swing/                       ← swing trading domain
│       │   ├── __init__.py
│       │   ├── scoring.py               ← from src/plutus/agents/scoring.py
│       │   ├── strategies/              ← from src/plutus/strategies/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── bundle_trend.py
│       │   │   ├── bundle_reversal.py
│       │   │   ├── bundle_breakout.py
│       │   │   ├── bundle_smc.py
│       │   │   ├── bundle_composite.py
│       │   │   ├── bundle_vcp.py
│       │   │   └── bundle_pead.py
│       │   ├── backtesting/             ← from src/plutus/backtesting/
│       │   │   ├── __init__.py
│       │   │   ├── runner.py
│       │   │   ├── paper_trader.py
│       │   │   └── walk_forward.py
│       │   ├── agents/                  ← LLM-powered analysis nodes
│       │   │   ├── __init__.py
│       │   │   ├── technical.py
│       │   │   ├── sentiment.py
│       │   │   ├── smart_money.py
│       │   │   ├── risk_manager.py
│       │   │   ├── synthesizer.py
│       │   │   ├── prompts.py
│       │   │   └── graph.py
│       │   ├── pipeline.py              ← extracted from main.py (weekly_pipeline swing section)
│       │   ├── outcomes.py              ← from src/plutus/weekly/outcomes.py (swing-specific)
│       │   ├── postmortem.py            ← from src/plutus/weekly/ (swing fine-tune)
│       │   └── triggers.py              ← swing alerts (PRE_SL_WARNING, TARGET1_HIT, ...)
│       │
│       ├── accumulation/                ← NEW domain
│       │   ├── __init__.py
│       │   ├── scoring.py               ← accum_classify + 3 pillars
│       │   ├── candidates.py            ← screen Nifty 100, rank, persist AccumulationCandidate rows
│       │   ├── tranches.py              ← position + tranche CRUD, avg cost recompute
│       │   ├── pipeline.py              ← weekly accumulation_run
│       │   └── triggers.py              ← T2/T3 trigger + bull-ready alerts
│       │
│       ├── api/                         ← FastAPI
│       │   ├── __init__.py
│       │   ├── routes.py                ← keep shared health/auth
│       │   ├── routes_swing.py          ← swing /analyze, /signals
│       │   └── routes_accumulation.py   ← NEW: /accumulation/candidates, /tranches
│       │
│       └── dashboard/                   ← Streamlit
│           ├── __init__.py
│           ├── app.py                   ← entry point (st.set_page_config + nav)
│           ├── home.py
│           ├── swing_signals.py
│           ├── swing_positions.py
│           ├── accumulation_candidates.py
│           ├── accumulation_tranches.py
│           ├── settings.py
│           ├── strategy_lab.py
│           └── components/
│               ├── __init__.py
│               ├── badges.py
│               ├── score_bars.py
│               ├── tranche_pips.py
│               ├── position_form.py     ← shared by swing + accumulation
│               └── regime_pill.py
│
├── tests/                               ← mirrors src/plutus structure
│   ├── conftest.py
│   ├── core/
│   ├── swing/
│   ├── accumulation/                    ← NEW
│   ├── api/
│   ├── dashboard/
│   ├── integration/                     ← spans multiple domains
│   ├── mocks/
│   └── fixtures/                        ← JSON/CSV test data
│
├── scripts/                             ← move from src/scripts/
│   └── refresh_seed_universe.py
│
├── deployment/                          ← keep as is
├── docs/                                ← NEW: move loose .md files here
│   ├── DASHBOARD_USER_GUIDE.md
│   ├── LOCAL_TESTING.md
│   └── PM_REVIEW.md
│
├── logs/                                ← gitignored, app writes here
├── data/                                ← gitignored, runtime caches
│   └── ohlcv_cache/                     ← was src/src/plutus/data/.cache
└── reports/                             ← gitignored, weekly outputs
    └── weekly/
```

## Dead code to delete

These are pre-existing and the user explicitly authorised removal. Delete in this phase, in one commit titled `phase 01: remove accidental nesting + stray test fixtures`.

| Path | Why dead |
|---|---|
| `src/src/` (entire tree) | Accidentally created by code with wrong cwd. After moving `.cache/` to `data/ohlcv_cache/`, the rest is empty. |
| `src/logs/` | Duplicates root `logs/`. Choose root; delete this. |
| `src/reports/` | Output dir nested in package. Move contents to root `reports/`, delete `src/reports/`. |
| `dashboard_test.png` (project root) | Stray test screenshot. |
| `test_buttons_interactive.py` (project root) | Belongs in `tests/dashboard/` or is obsolete. If it imports anything that still exists, move it; otherwise delete. |
| `test_dashboard_comprehensive.py` (project root) | Same rule as above. |
| `FINAL_SUMMARY.md` (project root) | Old handoff doc; superseded by this folder. |
| `TEST_REPORT.md` (project root) | Snapshot of one test run; stale. |
| `YFINANCE_ISSUES.md` (project root) | Issue log for a resolved fallback bug. |
| `__pycache__/` (project root) | Always. Add to `.gitignore` if missing. |

Files to **keep** at project root (do not delete): `main.py`, `README.md`, `LOCAL_TESTING.md` (move to `docs/`), `PM_REVIEW.md` (move to `docs/`), `DASHBOARD_USER_GUIDE.md` (move to `docs/`), `.env`, `.gitignore`, `local-test.sh`, `local-stop.sh`, `pytest.ini`, `deployment/`, `migrations/` (will move into `src/plutus/core/db/migrations/` as part of this phase).

## Tasks (in order)

### 01.1 — Snapshot before touching

```
git status            → must be clean (commit or stash current work first)
git checkout -b phase-01-restructure
pytest -q             → baseline: record passing count
```

Acceptance: 502 tests pass on the baseline (per recent runs in this session). If fewer pass, stop and fix before restructuring.

### 01.2 — Add packaging

Create `pyproject.toml` at project root with PEP 621 metadata. Source layout:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "plutus"
version = "0.2.0"
requires-python = ">=3.11"
dependencies = [
    # populate from current imports — see 01.3 to derive
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["plutus*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q"
```

Delete `pytest.ini` only if its config is migrated cleanly into `pyproject.toml`. Otherwise leave it as is and don't duplicate.

Test:
```bash
pip install -e .
python -c "import plutus; print(plutus.__file__)"
```

Acceptance: import resolves to `src/plutus/__init__.py`. No `ModuleNotFoundError`.

### 01.3 — Derive dependency list

Generate the actual imports used:

```bash
grep -rh "^import \|^from " src/ main.py tests/ \
  | grep -v "^from plutus\|^from \." \
  | awk '{print $2}' | cut -d. -f1 | sort -u
```

Cross-reference against the existing virtualenv (`pip freeze`). Write the dependency list into `pyproject.toml`. Pin to the **minor** version (e.g. `pandas>=2.2,<2.3`). Do not pin to the patch.

Acceptance: `pip install -e .` in a fresh venv installs everything `import` statements require. No missing imports when running `pytest --collect-only`.

### 01.4 — Move dead code out and delete

1. `mv src/src/plutus/data/.cache data/ohlcv_cache` (create `data/` if missing).
2. `rm -rf src/src`.
3. `rm -rf src/logs` (after confirming no test reads from it).
4. `mv src/reports/weekly reports/weekly` (create `reports/`), then `rm -rf src/reports`.
5. `mkdir docs && mv LOCAL_TESTING.md PM_REVIEW.md DASHBOARD_USER_GUIDE.md docs/`.
6. `rm FINAL_SUMMARY.md TEST_REPORT.md YFINANCE_ISSUES.md dashboard_test.png`.
7. Resolve `test_buttons_interactive.py` and `test_dashboard_comprehensive.py`:
   - If they import working modules: move to `tests/dashboard/` and update imports.
   - If they import deleted/stale modules: delete.
8. Update `.gitignore`:
   ```
   __pycache__/
   *.pyc
   .pytest_cache/
   logs/
   data/
   reports/
   .env
   .crew/
   *.png
   ```

Acceptance: `git status` shows only intended deletions and the `.gitignore`/dir moves. `pytest -q` still passes the same baseline (since no code moved yet, only output dirs).

### 01.5 — Create the target directory tree (empty)

Create all directories from the target layout with empty `__init__.py` files. No code moves yet. This is just a skeleton.

```
src/plutus/core/__init__.py
src/plutus/core/llm/__init__.py
src/plutus/core/db/__init__.py
src/plutus/core/db/models/__init__.py
src/plutus/core/data/__init__.py
src/plutus/core/alerts/__init__.py
src/plutus/core/utils/__init__.py
src/plutus/swing/__init__.py
src/plutus/swing/strategies/__init__.py
src/plutus/swing/backtesting/__init__.py
src/plutus/swing/agents/__init__.py
src/plutus/accumulation/__init__.py
src/plutus/dashboard/components/__init__.py
tests/core/__init__.py
tests/swing/__init__.py
tests/accumulation/__init__.py
tests/integration/__init__.py
tests/fixtures/__init__.py
```

Acceptance: `find src/plutus -type d` matches the target layout (minus the still-old files at the original locations). `pytest -q` still green.

### 01.6 — Move modules into core

Use `git mv` (preserves history). One commit per logical move. Order matters — move dependencies before dependents.

```
git mv src/plutus/config.py             src/plutus/core/config.py
git mv src/plutus/config_params.py      src/plutus/core/config_params.py
git mv src/plutus/agents/openrouter_client.py  src/plutus/core/llm/openrouter_client.py
git mv src/plutus/data                  src/plutus/core/data
git mv src/plutus/db                    src/plutus/core/db
git mv src/plutus/alerts                src/plutus/core/alerts
git mv migrations                       src/plutus/core/db/migrations
```

After each move, find and fix imports across the project:

```bash
# canonical sweep — run after every move
grep -rln "from plutus.config\b\|from plutus\.config import" src/ tests/ main.py
# then sed-replace to the new path
```

**Constraint:** The AngelOne block in `core/data/ohlcv.py` must be byte-identical to the original `src/plutus/data/ohlcv.py`. Verify with `git diff --stat src/plutus/data/ohlcv.py src/plutus/core/data/ohlcv.py` — it should be 0 lines changed (only path metadata).

Then split `core/db/models.py` per the target layout:

- `core/db/base.py` — `Base`, `SessionLocal`, `engine`, `init_db()`.
- `core/db/models/shared.py` — `WeeklyRun`, `TradingParam`, `MockPortfolio`, `PaperTrade`, `Alert`, `MarketRegimeSnapshot`.
- `core/db/models/swing.py` — `Recommendation`, `RejectedHeadline`.
- `core/db/models/__init__.py` — re-exports every public model so `from plutus.core.db.models import Recommendation` still works.

This is a *split*, not a *rewrite*. No column changes. No relationship changes.

Acceptance after every move + import fix: `pytest -q` matches baseline.

### 01.7 — Move modules into swing

```
git mv src/plutus/agents/scoring.py     src/plutus/swing/scoring.py
git mv src/plutus/agents/technical.py   src/plutus/swing/agents/technical.py
git mv src/plutus/agents/sentiment.py   src/plutus/swing/agents/sentiment.py
git mv src/plutus/agents/smart_money.py src/plutus/swing/agents/smart_money.py
git mv src/plutus/agents/risk_manager.py src/plutus/swing/agents/risk_manager.py
git mv src/plutus/agents/synthesizer.py src/plutus/swing/agents/synthesizer.py
git mv src/plutus/agents/prompts.py     src/plutus/swing/agents/prompts.py
git mv src/plutus/agents/graph.py       src/plutus/swing/agents/graph.py
git mv src/plutus/strategies            src/plutus/swing/strategies
git mv src/plutus/backtesting           src/plutus/swing/backtesting
git mv src/plutus/weekly/outcomes.py    src/plutus/swing/outcomes.py
git mv src/plutus/weekly/postmortem.py  src/plutus/swing/postmortem.py  # if it exists
```

Extract `swing/pipeline.py` from `main.py`:
- Move the swing-run block (currently roughly lines 73–213 per phase 7 wiring) into `plutus.swing.pipeline.run_weekly_swing(db_session, run_date)`.
- `main.py` becomes a thin orchestrator: imports + scheduler wiring + calling the two domain pipelines.

Extract `swing/triggers.py` from `core/alerts/monitor.py`:
- The per-trade checks (PRE_SL_WARNING, TARGET1_HIT, etc.) move into `swing.triggers.check_swing_position(...)`.
- `core/alerts/monitor.py` becomes a generic loop that calls registered checker functions. Each domain registers its checker at module import time.

Acceptance: `pytest -q` passes. `python -m plutus.swing.pipeline --dry-run` runs the swing pipeline end-to-end without errors against a seeded DB.

### 01.8 — Re-run + commit

After all moves and import sweeps:

```bash
pytest -q                              # must match baseline pass count
python -c "import plutus.swing.pipeline; import plutus.core.db.models"
python main.py --health-check          # add this flag in 01.7 if not present
git add -A
git commit -m "phase 01: restructure into core + swing domains; remove stray code"
```

## Verification gate for phase 01

- [ ] `pyproject.toml` builds and `pip install -e .` succeeds in a fresh venv.
- [ ] `pytest -q` passes the same count as the pre-restructure baseline.
- [ ] `find src/plutus -name "*.py" -path "*/plutus/agents/*" 2>/dev/null` returns 0 files (old `agents/` gone).
- [ ] `find . -type d -name src -path "*/src/src" 2>/dev/null` returns 0 results.
- [ ] `git log --diff-filter=D --name-only` includes `FINAL_SUMMARY.md`, `TEST_REPORT.md`, `YFINANCE_ISSUES.md`, `dashboard_test.png`.
- [ ] The AngelOne rate-limit block in `core/data/ohlcv.py` is byte-identical to the original (`git log -p` shows only path change, not content).
- [ ] `python -c "from plutus.core.db.models import Recommendation, MockPortfolio, WeeklyRun, TradingParam, Alert"` succeeds.
- [ ] `python -c "from plutus.swing.scoring import compute_score; from plutus.swing.strategies.runner import run_bundle"` succeeds.

Do not start phase 02 until every box is checked.
