# P1 — Swing Sentiment (spec 09 §2–5)

## Status: COMPLETE ✅

Implemented Plutus v2 swing sentiment with TDD (tests written first). All 28 tests pass; ruff + mypy clean. Branch `v2-rebuild`.

## Implemented files

### Source (`src/plutus/swing/sentiment/`)
- `types.py` — `Headline(source, published_at, title, body, entities)` frozen dataclass. Self-contained (does not depend on `data/news.py`) per A8 isolation.
- `scorer.py` — `SentimentTiers`, `SentimentScore(score_0_5, raw_score, headline_count, fired_keywords)`, `SentimentScorer.score()`. Deterministic keyword scoring; **contribution capped at 5** (A8 weight cut), derived from `settings.sentiment_pillar_weight * 100` (no magic number). Tiers injectable via constructor.
- `entity_resolver.py` — `EntityMatch(confidence)`, `EntityResolver.resolve()`. Exact symbol, company-name/alias map (`L&T`→`LARSEN`), and context-token disambiguation for ambiguous `TCS` (IT/software → high; telecom/communications → low). Only `high` counts for corroboration.
- `corroboration.py` — `HardKillVerdict(fires, reason, penalty_only)`, `HardKillEvaluator.evaluate()`. Fires only on (1) ≥2 independent high-conf entity headlines (different source domains), (2) ≥1 high-conf headline + gap-down on >1.5× delivery-adjusted volume, or (3) structural event class. Else graded penalty 0–3, no kill.
- `color.py` — `SentimentColor(narrative: str)`, `SentimentColorist.narrate()`. **Text-only output**; LLM client is an injectable `Callable[[str], str]` with an offline default (no network in tests).

### Tests (`tests/swing/sentiment/`) — 28 tests, 4 hallmarks
- `test_scorer.py` — positive/negative scoring; **cap-at-5 (A8 hallmark)**; zero-floor; custom tiers.
- `test_scorer_no_llm_input.py` — AST assert scorer.py + corroboration.py do not import `color`/`llm`.
- `test_entity_resolver.py` — exact, alias, TCS context disambiguation.
- `test_corroboration_two_headlines.py` — two independent → fires; same source → does not.
- `test_corroboration_headline_plus_volume.py` — gap-down + volume → fires; flat → does not.
- `test_corroboration_structural_event.py` — rating downgrade → fires; other symbol → does not.
- `test_corroboration_uncorroborated.py` — single match → graded penalty (no kill); penalty capped at 3; empty → 0.
- `test_color_is_color_only.py` — **(A8/C6 hallmark)** `SentimentColor` has only the `narrative: str` field; `narrate()` returns color offline; AST walk over `swing/scoring/` shows no import of `color.py`.

## Verification
- `pytest tests/swing/sentiment/ -q` → **28 passed**
- hallmark subset → **4 passed**
- `ruff check` → clean
- `mypy` → no issues (6 source files)
- Invariant greps confirm: scorer/corroboration import no `color`/`llm`; scoring dir imports no `sentiment.color`.

## Notes / decisions
- `Headline.entities` accepted as a "high-confidence" entity-list match (deterministic NER output), in addition to text-based resolution.
- "Independent" sources = distinct source domains (`_source_domain`).
- "Gap-down" = today's open below prior close (any amount); high volume = >1.5× prior delivery-adjusted volume.
- Did **not** modify `settings.py` (used existing `sentiment_pillar_weight`, `sentiment_hard_kill_requires_corroboration`).

## Blockers
None.
