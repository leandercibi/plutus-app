# 00 — Coding Principles

> Read this first. Every later doc assumes you have internalized these.
> The bible is `docs/PLUTUS_CONSOLIDATED_REVIEW.md`. Do not change any logic prescribed there.

---

## 1. Karpathy guidelines (binding)

These override personal style. Source: Andrej Karpathy's observations on LLM coding pitfalls.

1. **Think before coding.** State assumptions explicitly. If two interpretations exist, surface both — never pick silently. If unclear, stop and ask in a comment block at the top of the file you were about to write.
2. **Simplicity first.** Minimum code that solves the problem. No speculative abstractions, no "flexibility" not requested, no error handling for impossible scenarios.
3. **Surgical changes.** Touch only what the task names. Don't refactor adjacent code. Don't reformat. Match existing style.
4. **Goal-driven execution.** Every task is "write the failing test → make it pass → verify." No green-without-verifying. No "make it work" — replace with a checkable predicate.

If you write 200 lines where 50 would do, delete and rewrite.

---

## 2. Test-driven development (binding)

**Rule of order:** test file exists and fails before the implementation file exists. No exceptions.

```
1. Write test_X.py with the failing test (red).
2. Write the minimum X.py to pass (green).
3. Refactor only what your green code introduced (refactor).
4. Move to next test.
```

Acceptance criteria per module are listed in that module's spec doc. If you implement a method not listed there, you have escaped scope — stop and re-read the spec.

**Determinism:** every test that touches randomness, time, or external data must seed/freeze. Use `freezegun` for `datetime.now()` and `np.random.default_rng(seed)` for RNG. No flaky tests.

**Fixtures over mocks.** Real OHLCV fixtures (small, checked-in parquet) > mocked DataFrames. See `TESTING.md` for the fixture catalog.

**Coverage:** 90% line coverage on `swing/`, `accumulation/`, `shared/`. 80% elsewhere. Coverage is a floor, not a goal.

---

## 3. Domain-driven module boundaries

```
shared/        cross-cutting, knows no domain
swing/         day-to-week trades, bundle-based entries, expectancy-gated
accumulation/  multi-month tranches, fundamental + RS, thesis-invalidated
```

**Direction of imports** (strict, enforced by an import-linter rule in CI):

```
dashboard/ api/ alerts/ scheduler/   ← may import from anywhere below
swing/ accumulation/                  ← may import from shared/, data/, db/
shared/                               ← may import from data/, db/
data/ db/ config/                     ← leaves; no upward imports
```

`swing/` may NOT import from `accumulation/` and vice versa. If you need cross-domain logic, it belongs in `shared/`.

---

## 4. The no-LLM-leak rule (binding, from review §A8 / C6)

**No LLM output may produce a value that gates or flips a classification.**

The review documents that the v1 engine has three LLM leaks (sentiment material-event flag, smart-money pillar input, technical entry/stop/target writer). All three are closed in v2:

- Deterministic scorers compute every score, gate, and label.
- LLM nodes may produce **color text only** — rationale strings, narrative paragraphs, summaries. These are display-only.
- If an LLM-produced value enters a numeric computation that affects BUY/WATCH/AVOID, that is a bug. CI fails the build via a static-analysis rule: any function whose call graph reaches `llm/` may not return into a `score_*`, `classify_*`, `gate_*`, or `decide_*` function.

---

## 5. Configuration and contradictions

The review flagged the **2% vs 5% per-trade risk** contradiction (A6). The cure is structural, not editorial:

- Every tunable lives in `config/settings.py` as a Pydantic `Settings` field.
- No magic numbers in code. `risk_per_trade_pct` lives in one place; everything reads it.
- If the value appears in two places, CI fails (lint rule: `grep -r "0\.0[12]" src/ --include="*.py" | grep -v config` returns empty).
- Defaults pinned in code; overrides via `.env`.

---

## 6. Error policy

- **System boundaries** (network, file, DB, user input): validate, catch, log, surface.
- **Internal calls** (one module to another in the same domain): trust the contract. No defensive `if x is None`. If the contract is wrong, the type checker catches it.
- **Never swallow.** No bare `except:` and no `except Exception: pass`. If you catch, you must either re-raise with context, return a typed error, or log + recover with an explicit recovery action.
- **Fail loud in dev, fail safe in prod.** A signal-generation failure on one stock must not stop the run; the run logs the failure and continues. Aborts only on freshness-assertion failure (B11) — a stale candle invalidates the entire batch.

---

## 7. Logging

- Use `logging.getLogger(__name__)`. No `print`.
- One `logs/YYYY-MM-DD/app.log` per run day. Rotated nightly.
- `INFO` = lifecycle events (run start, stock processed, signal generated).
- `WARNING` = recoverable anomalies (provider fallback, stale cache hit).
- `ERROR` = a stock or bundle was dropped; the run continues.
- `CRITICAL` = run aborted (freshness, config invalid, DB unreachable).
- Every log line is structured: `module=...`, `stock=...`, `bundle=...`, `run_id=...`. Use `logger.info("...", extra={...})`, not f-strings inside the message.

---

## 8. Typing

- `from __future__ import annotations` in every file.
- All public functions and methods carry full type hints. Internal helpers may infer.
- Pydantic models for every data-record that crosses a module boundary (signals, fills, scores, calibration rows).
- `mypy --strict` on `shared/`, `swing/`, `accumulation/`, `config/`. CI gate.

---

## 9. Naming

- Modules: `snake_case`, singular (`bundle.py`, not `bundles.py` when the module defines one class). Use plural only for collections (`bundles/` package).
- Classes: `PascalCase`, intention-revealing — `TrendBundle`, not `Bundle1`.
- Functions: `verb_noun` — `score_pillar`, `compute_expectancy`, `apply_cost_model`.
- Predicates: `is_*` / `has_*` / `should_*` — return `bool`.
- Constants: `UPPER_SNAKE_CASE`.
- No abbreviations except domain-native ones (`RR`, `SL`, `ATR`, `ADV`, `MFE`, `MAE`, `OOS`, `PIT`, `FII/DII`, `D/E`, `VCP`, `PEAD`, `SMC`).

---

## 10. Comments

Default to **no comments**. A well-named function does not need a comment. A comment is appropriate only when:

- A non-obvious WHY (an exchange quirk, a workaround for a provider bug, a safety invariant).
- A pointer to the review item it implements: `# implements review A4 (expectancy gate)`. Keep these — they trace code to bible.
- Never explain WHAT — if the reader can't tell from names, rename.

No multi-line docstrings unless the function is a public API consumed outside its module.

---

## 11. Surgical-change discipline (from §3 above, expanded)

When fixing one item from the action plan:

- Do not "improve" adjacent code.
- Do not delete code marked for deletion in a different task — that task owns it.
- If you notice a problem not in your scope, add a one-line `# TODO(review-XX): ...` and move on. Do not chase.
- Every line of your diff must trace to a numbered review item (A/B/C/D/E…) or a TDD test you are making pass.

---

## 12. Definition of done (per spec doc)

A spec doc's items are "done" when:

1. Every class/method enumerated in the doc has a corresponding test that fails without the implementation.
2. `pytest`, `mypy --strict`, `ruff check`, and the import-linter pass.
3. Coverage threshold met.
4. The spec doc's "acceptance criteria" section is checked off in the PR description.
5. No `TODO` left in the diff for items the doc says you finished.
