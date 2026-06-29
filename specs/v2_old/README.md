# Plutus v2 — Restructure + Accumulation Mode

## Who reads this

You are the implementing agent. Read every file in this folder before writing code. They are sequenced. Do not skip ahead.

```
00-coding-principles.md      → rules every change obeys
01-repo-restructure.md       → new folder layout, packaging, dead-code removal
02-core-domain.md            → shared infrastructure (data, db, alerts, llm)
03-swing-domain.md           → swing trading domain (mostly moves)
04-accumulation-domain.md    → NEW domain (scoring, candidates, tranches, pipeline, alerts)
05-dashboard.md              → dual-mode Streamlit dashboard
06-testing-strategy.md       → TDD discipline, fixtures, coverage targets
07-acceptance-checklist.md   → end-to-end gate before declaring done
```

## What "done" means

The acceptance checklist in `07-acceptance-checklist.md` is the gate. Every item must pass — no partial credit, no "I'll come back to it". If you can't pass an item, stop and ask, do not paper over.

## How to work

1. Read all 8 files top to bottom once.
2. Implement phase by phase, in order. Each phase has a test-first contract — write the failing test, then write the code to make it pass.
3. Run the test for the current phase before moving on.
4. Never start a new phase with the previous phase's tests failing.

## Reference material outside this folder

- `/Users/leander/.claude/plans/first-the-scale-you-hazy-naur.md` — original overhaul plan with Phase 9 PRD/tech doc. Treat as background; this folder is the authoritative spec.
- `specs/PRD_PHASE2.md`, `specs/overhaul/`, `specs/phase2/` — historical context. Read only if a current spec file points you there.

## What is intentionally NOT in scope

- Real broker order execution.
- Auto-rebalancing between swing and accumulation pools.
- Reddit sentiment.
- Options / F&O / pair trading.
- Auto-tuning of weights or thresholds (the manual postmortem loop from Phase 4.5 stays as-is).

## What this restructure is NOT

It is not a rewrite. The swing pipeline, scoring rubric, backtest harness, alert system, and dashboard already work. We are:

1. Moving files into a clearer layout.
2. Adding a clean second domain (accumulation) alongside swing.
3. Removing the obvious accidental cruft (`src/src/`, duplicate logs, stray screenshots).
4. Backing every move with tests so nothing silently regresses.

If a temptation arises to "clean up while I'm here" — resist. Karpathy rule #3 applies. Surgical changes only.
