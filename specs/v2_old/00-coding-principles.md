# 00 — Coding principles

These rules apply to every change in this restructure. They override personal preference.

## The four karpathy guardrails (non-negotiable)

### 1. Think before coding
- State assumptions in your turn before writing code. If two readings of a spec exist, pick one explicitly and say so.
- If a spec is ambiguous, stop and ask. Do not guess.
- If a simpler approach exists than what is written, propose it before implementing.

### 2. Simplicity first
- Minimum code that satisfies the test. Nothing speculative.
- No abstractions for single-use code. A second user must exist before you generalise.
- No flags, config knobs, or "extensibility hooks" that the spec did not name.
- No error handling for impossible scenarios. Validate at boundaries, trust the inside.
- If you wrote more than 200 lines and feel it could be 50, rewrite it before committing.

### 3. Surgical changes
- Touch only what the current phase requires.
- Do not "improve" adjacent code, formatting, or comments. Match the existing style even when you disagree.
- When your change orphans an import or variable, delete the orphan. Do not delete pre-existing dead code unless `01-repo-restructure.md` lists it explicitly.
- Every changed line traces to a spec sentence or a failing test.

### 4. Goal-driven execution
- Every spec phase has a verification command (a `pytest` invocation or a CLI run). Run it before moving on.
- For each function you add: write the failing test first, watch it fail, then write the code. Watch it pass. Then move on.
- Multi-step phases: list the steps as a TaskCreate plan and tick them off in order.

## Project-specific rules

### Rule A — AngelOne rate limiting is frozen

The rate-limit constants in `src/plutus/data/ohlcv.py` are locked:

```python
_ANGEL_RATE_LOCK = __import__('threading').Lock()
_ANGEL_LAST_CALL = [0.0]
_ANGEL_MIN_INTERVAL = 0.4          # 2.5 req/sec
_ANGEL_MINUTE_WINDOW: list = []
_ANGEL_MINUTE_LIMIT = 170          # 10-call buffer under 180/min
```

Do not change them. Do not "improve" the locking strategy. If a phase moves this file, the constants and their values move with it byte-for-byte.

### Rule B — No new LLM calls without a flag

Every LLM call costs money and time. New call sites land behind a config flag (default OFF) that the user toggles in Settings. Document the flag and its default in the phase spec when you introduce the call site.

### Rule C — Domain isolation

`swing` does not import from `accumulation`. `accumulation` does not import from `swing`. Both import from `core`. If you find yourself reaching across, that is a signal the shared logic belongs in `core`.

### Rule D — Tests live next to their domain

```
tests/core/...           ← shared infra tests
tests/swing/...          ← swing domain tests
tests/accumulation/...   ← accumulation domain tests
tests/dashboard/...      ← UI tests
```

A test that imports from both `swing` and `accumulation` is integration-level; it goes in `tests/integration/`. We prefer many small unit tests over a few large integration tests.

### Rule E — Time + money values are explicit

- Money: `Decimal` for persisted balances, `float` for transient calculations is acceptable. Never store `float` in DB for ₹ amounts.
- Dates: store as `DATE` (no timezone). Times as UTC. Convert to IST only at display boundaries.
- Round only at display. Storage keeps the precision the calculator produced.

### Rule F — No new top-level dependencies without justification

Before adding a Python package to the project, check:
1. Is the equivalent already a transitive dep? (`pip show` it.)
2. Is the use a one-liner that doesn't justify a dep?

If you add a dep, add it to `pyproject.toml` in the same commit. No standalone `pip install`.

### Rule G — Migrations are forward-only

Once a migration file is committed and applied anywhere, it is frozen. Bugs in a migration are fixed by writing the next migration, not by editing the old one. File names follow `NNN_short_name.sql` in lexicographic order.

### Rule H — Names

- Modules and packages: `snake_case`.
- Classes: `PascalCase`.
- Functions and variables: `snake_case`.
- Constants: `SCREAMING_SNAKE_CASE`.
- Test files mirror the module under test: `src/plutus/accumulation/scoring.py` → `tests/accumulation/test_scoring.py`.

### Rule I — Comments

The project default is no comments. Write one only when the *why* is non-obvious — a subtle invariant, a workaround for a specific upstream bug, or a measurement that justified an unusual constant. Comments that paraphrase the code are deleted. Doc strings on public functions are fine when they document the contract, not when they restate the signature.

### Rule J — One PR per phase

Each spec file in this folder is one phase. One phase = one logical commit (or PR, if you push). Mixing phases in a single commit makes review impossible. The commit message names the phase: `phase 04: accumulation scoring module`.

## TDD discipline

For every new function, the workflow is:

1. Open the test file. Write the test. Write a docstring saying what behaviour is being verified.
2. Run the test. Confirm it fails for the right reason (assertion error, not import error).
3. Write the minimum implementation that makes the test pass.
4. Re-run the test. Confirm it passes.
5. Repeat for the next behaviour.

Skip TDD only for pure file moves (no logic change). A pure move's test is "the import resolves at the new path and existing tests still pass."

## When you're stuck

If you've spent 30 minutes on a single decision, stop and ask. Do not power through. The cost of asking is one short message. The cost of guessing wrong is unwinding hours of code.
