# Plutus — Coding Standards

**Read this before writing or modifying any code in `plutus-app`.** These are enforceable
rules derived from the existing codebase, not aspirations. When in doubt, match the
patterns in the files this document cites. Use `MUST` / `SHOULD` in the RFC-2119 sense.

If you find code that violates these rules, do **not** silently "fix" unrelated files —
note it and stay scoped to your task. New and edited code MUST comply.

---

## 0. Pre-implementation checklist

Before you write code, and again before you consider a change done:

- [ ] Read `HANDOFF.md` for current branch state, open issues, and known bugs.
- [ ] Identify which architectural **layer** your change lives in (§3) and confirm you are
      not introducing an illegal import direction.
- [ ] Backend: does a Pydantic **schema** already exist for the shape you're returning? Reuse it.
- [ ] Frontend: does a **hook** in `src/api/hooks.ts` already fetch this data? Reuse it.
- [ ] After editing, run the gates for the side you touched (§9). A change is not "done"
      until `ruff`, `mypy`, `import-linter`, `pytest` (backend) or `tsc -b` + `eslint`
      (frontend) pass.
- [ ] Never commit secrets. Config comes from `Settings` / env, never hard-coded.

---

## 1. Git workflow & branching (ENFORCED)

- **`main` is protected. Never push directly to `main`.** All work — features, fixes,
  chores — happens on a branch and lands via a **Pull Request**.
- Branch from up-to-date `main`. Name branches `type/short-description`, e.g.
  `feat/exit-monitor-trailing-stop`, `fix/signal-dedup`, `chore/bump-deps`,
  `ci/…`, `docs/…`.
- Keep a branch scoped to one logical change. Rebase or merge `main` in to stay current.
- A PR MUST be green on CI (`ci.yml` — the §9 gates) before it can merge. Merging a PR to
  `main` triggers automatic deployment to the OCI server (`deploy.yml`), so **main must
  always be deployable.**
- Commit messages: imperative mood, one concern per commit. Reference the issue/bug id
  when there is one.

---

## 2. Repository layout

```
backend/
  src/plutus/           # the Python package (src-layout, installed with `pip install -e ".[dev]"`)
    api/                # FastAPI routers + api/schemas/ (Pydantic request/response models)
    scheduler/          # APScheduler jobs — the pipeline entry points
    pipeline/           # orchestration (sunday run, exit monitor)
    swing/  accumulation/   # the two independent strategy domains
    shared/             # cross-strategy domain logic (scoring, regime, fills, types)
    data/               # market-data providers, freshness, calendar, breadth, news
    db/                 # SQLAlchemy Base, models, session
    config/             # Settings (pydantic-settings), logging
    llm/  alerts/  backtesting/  dashboard/
  tests/                # mirrors the package tree (tests/api, tests/swing, …)
frontend/
  src/
    api/                # client.ts (axios) + hooks.ts (TanStack Query)
    pages/  components/  store/  types/  styles/
```

- Backend is **src-layout**. Import as `from plutus.x import y`, never by file path.
- `tests/` mirrors `src/plutus/`: a change in `plutus/swing/foo.py` gets tests in
  `tests/swing/`.

---

## 3. Backend architecture & layering (ENFORCED by import-linter)

`backend/importlinter.ini` enforces a strict layer order. Higher layers may import lower
layers; **lower layers MUST NOT import higher ones.**

```
scheduler
  api
    dashboard | alerts
      swing | accumulation
        shared
          data
            db
              config
```

Hard rules:

- **`swing` and `accumulation` MUST NEVER import each other.** They are independent domains.
  Shared logic goes in `shared/`.
- `config`, `db`, `data` are foundational — they MUST NOT import strategy or api code.
- If you feel you need an upward import, you're putting the code in the wrong layer.
  Move the shared piece down into `shared/` (or lower) instead.
- The only sanctioned exception is already listed in `importlinter.ini`
  (`regime_builder → shared.regime.detector`). Do not add new exceptions without updating
  that file and explaining why.

---

## 4. Python style

### 3.1 Formatting & linting

- **ruff** is the single source of truth (`backend/ruff.toml`). Line length **100**.
  Selected rule sets: `E, F, I, UP, B, SIM, C4`. Run `ruff check .` and `ruff format .`.
- Target **Python 3.11** syntax (`X | None`, `list[int]`, `dict[str, Any]` — never
  `Optional`, `List`, `Dict` from `typing`).
- Every module starts with `from __future__ import annotations` as the first import line.
  (See any file under `src/plutus/`.)
- Double quotes for strings (ruff format default).

### 3.2 Typing

- **mypy runs `strict = True`** for `plutus.shared.*`, `plutus.swing.*`,
  `plutus.accumulation.*`, and `plutus.config.*` (`backend/mypy.ini`). Code in these
  packages MUST be fully typed — every function has annotated params and a return type.
- All new public functions get explicit return types regardless of package.
- Use `cast(...)` only at genuine type-narrowing boundaries (see `api/swing.py`), not to
  paper over bad types.

### 3.3 Naming & structure

- Module-private helpers are prefixed with `_` (`_signal_out`, `_as_int`, `_request_id`).
- Module-level constants are `UPPER_SNAKE` (`_CLOSED_STATES`).
- Prefer small pure helper functions that map a DB row → a Pydantic `*Out` model, as in
  `api/swing.py::_signal_out`. Keep route handlers thin.

---

## 5. Backend: FastAPI

### 4.1 Routers

- One router per domain file in `api/`. Declare it with prefix, tags, and auth up front:

  ```python
  router = APIRouter(prefix="/swing", tags=["swing"], dependencies=[Depends(require_token)])
  ```

- Every route MUST declare an explicit `response_model` and an annotated return type.
- DB access is via the dependency: `db: Session = Depends(get_db)`. Never open a session
  inside a handler; `get_db` (overridable in tests) owns the lifecycle.
- Query params use `Query(default=..., description=...)`. (`B008` is intentionally ignored
  for `api/**` because FastAPI puts `Depends()`/`Query()` in argument defaults by design.)
- Register new routers in `api/main.py::create_app` via `app.include_router(...)`.

### 4.2 Schemas (request/response models)

- Pydantic request/response models live in **`api/schemas/`**, separate from SQLAlchemy
  models in `db/models.py`. Do not return ORM objects directly.
- Naming convention: response models end in **`Out`** (`SwingSignalOut`, `PillarBreakdownOut`),
  request bodies end in **`In`** (`EnterFromSignalIn`, `ManualExitIn`).
- Convert ORM → schema with an explicit helper; do not rely on implicit attribute mapping
  for anything non-trivial.

### 4.3 Errors

- Error handling is centralized in `api/errors.py`. All errors serialize to the `ErrorOut`
  shape: `{ code, message, request_id }`. Do not invent ad-hoc error JSON.
- Raise `HTTPException` for expected client errors. Unhandled exceptions are caught by the
  fallback handler, which logs the full trace and returns a sanitized 500 — **never leak
  internal detail or stack traces in a response body.**

---

## 6. Backend: database

- **SQLAlchemy 2.0 declarative style only**: `class Base(DeclarativeBase)`, typed
  `Mapped[...]` attributes, `mapped_column(...)`. No legacy `Column(...)` / `declarative_base()`.
- **Money and prices use `Decimal` mapped to `Numeric(precision, scale)`** (e.g.
  `Numeric(20, 2)` for INR values, `Numeric(14, 2)` for prices). Never store currency as
  `float`. Ratios/percentages that aren't money may be `float`.
- Add integrity constraints in `__table_args__`: `UniqueConstraint`, `CheckConstraint`
  (name them `ck_*`), and `index=True` on columns you filter/join on.
- Add a one-line docstring on tables explaining what one row represents and any spec
  reference (see `Universe`, `RegimeSnapshot`).
- Schema changes go through **Alembic** (`backend/alembic/`). Never mutate a shipped table
  by editing the model alone — generate a migration.

---

## 7. Backend: config, logging, tests

- **All configuration flows through `config/settings.py::Settings`** (pydantic-settings).
  Add a typed field with a sane default and a section comment; use `Literal[...]` for
  enumerated values and `SecretStr` for secrets. Read settings via `get_settings()`
  (LRU-cached) or the `get_app_settings` dependency. Never read `os.environ` directly in
  domain code, and never hard-code tunables (risk %, capital, cost model, thresholds).
- Logging via `logging.getLogger(__name__)`. Use `logger.exception(...)` in error paths.
- **pytest markers are strict** (`--strict-markers`): tag every test with one of
  `unit`, `integration`, `property`, `slow`, `hallmark` (see `pytest.ini`).
  - `unit` = no IO, no DB. `integration` = real SQLite/Postgres test DB.
  - `property` = hypothesis. `slow` (>1s) is excluded from the default run.
- Override the DB in tests through `app.dependency_overrides[get_db]`, not by patching
  internals.

---

## 8. Frontend (React 19 + TS + Vite + Tailwind v4)

### 7.1 TypeScript

- `tsconfig` is **strict**, with `noUnusedLocals`, `noUnusedParameters`,
  `noFallthroughCasesInSwitch`. Unused imports/vars are build errors — clean them up.
- Import types with `import type { ... }`. Shared API types live in `src/types/api.ts`;
  reuse them, don't redeclare shapes inline.
- Style: 2-space indent, single quotes, **no semicolons** (match existing files). Numeric
  literals for time use underscores: `60_000`, `5 * 60_000`.

### 7.2 Data fetching — the one hard rule

- **All server communication goes through the axios instance in `src/api/client.ts` and
  the TanStack Query hooks in `src/api/hooks.ts`.** Components MUST NOT call `axios`/`fetch`
  directly.
- `client.ts` interceptors already attach the bearer token and handle 401 → logout. Do not
  reimplement auth per-call.
- Add a new endpoint as a `useXxx` hook:
  - `useQuery` for reads, `useMutation` for writes (invalidate affected `queryKey`s on success).
  - `queryKey` is an array, most-general segment first: `['chart', symbol, signalId, days]`.
  - Choose `staleTime` / `refetchInterval` deliberately. LLM-backed endpoints are cached
    server-side — use long `staleTime` and `retry: false` so you don't re-bill the model
    (see the AI-summary hooks and their comments).
  - For optional/gated fetches use an `enabled` guard (`enabled: !!symbol && enabled`).

### 7.3 State, components, styling

- Global client state (auth) uses **Zustand** with `persist` (`src/store/auth.ts`).
  Don't put server data in Zustand — that's TanStack Query's job.
- Reusable presentational pieces live in `src/components/ui|layout|chart`. Pages compose
  them; keep pages focused on data + layout.
- **Colors come from the design tokens** in `src/styles/tokens.ts` / CSS variables
  (`var(--green)`, `var(--muted)`, …). Prefer these over new hard-coded hex values so the
  dark theme stays consistent.
- Handle the three states every query has: loading (`<Skeleton />`), error
  (`<ErrorBanner />`), and empty — don't render against `undefined` data.

---

## 9. Definition of done — run the gates

Run from the relevant directory. All must pass before a change is complete.

**Backend** (`cd backend`):
```bash
ruff format . && ruff check .
mypy src
lint-imports                 # import-linter: enforces the layering in §3
pytest                       # respects markers; slow tests excluded by default
```

**Frontend** (`cd frontend`):
```bash
npm run build                # tsc -b && vite build — type errors fail the build
npm run lint                 # eslint
```

---

## 10. Golden rules (the short version)

1. Stay in your layer. `swing` ⟂ `accumulation`. Lower layers never import up.
2. Money is `Decimal`/`Numeric`, never `float`. Tunables live in `Settings`, never inline.
3. Backend returns Pydantic `*Out` schemas, not ORM rows. Errors use the `ErrorOut` shape.
4. Frontend talks to the server only through `hooks.ts` + `client.ts`. One hook per endpoint.
5. Full typing in strict packages; `from __future__ import annotations` everywhere.
6. Tests mirror the tree and carry a marker. Schema changes ship with an Alembic migration.
7. A change isn't done until the §9 gates pass. Read `HANDOFF.md` first.
