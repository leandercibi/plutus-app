# 09 — Sentiment & Smart Money

> Sentiment under `swing/sentiment/` (swing-only consumer). Smart Money under `shared/smart_money/` (consumed by both, weighted differently). Implements A7 (FII/DII relocated), A8 (sentiment 5% + corroborated hard-kill + deterministic-only gating), A9 (delivery feed wired into volume gate), C1 (raw FII/DII removed from per-stock pillar).

---

## 1. Module layout

```
src/plutus/swing/sentiment/
├── __init__.py
├── scorer.py             # deterministic keyword/tier scorer (the gating path)
├── corroboration.py      # A8 — two-source / price+volume / structural confirm
├── entity_resolver.py    # deterministic NER for symbol resolution
└── color.py              # LLM-narration adapter; output is text only

src/plutus/shared/smart_money/
├── __init__.py
├── delivery.py           # delivery-trend pillar input
├── bulk_block.py         # bulk + block deal pillar input
├── mf_accumulation.py    # MF accumulation verdict with age-decay
└── per_stock_score.py    # composes the 3 above into a per-stock flow score
```

FII/DII is **not** in `shared/smart_money/` — it lives in `shared/regime/` per A7. CI check: `grep -r "fii\|dii" src/plutus/shared/smart_money/` returns nothing.

---

## 2. Sentiment scorer (`swing/sentiment/scorer.py`) — A8

```python
@dataclass(frozen=True)
class SentimentTiers:
    positive_keywords: dict[str, int]   # keyword -> weight
    negative_keywords: dict[str, int]
    structural_events: set[str]         # "rating_downgrade", "exchange_filing_adverse", ...

@dataclass(frozen=True)
class SentimentScore:
    score_0_5: int                      # capped at 5 of 100 (A8 weight cut)
    raw_score: int                      # uncapped, kept for diagnostics
    headline_count: int
    fired_keywords: list[str]

class SentimentScorer:
    def score(self, headlines: list[Headline], symbol: str) -> SentimentScore:
        """Deterministic. Weight-cut: max contribution to swing total is 5 (A8)."""
```

**The LLM (`color.py`) does NOT feed into this scorer.** It is a separate adapter that produces narrative paragraphs for the dashboard; nothing it returns is a numeric input to the pillar.

---

## 3. Corroboration (`corroboration.py`) — A8

```python
@dataclass(frozen=True)
class HardKillVerdict:
    fires: bool
    reason: Literal["two_entity_headlines", "headline_plus_pricevol", "structural_event", "uncorroborated"]
    penalty_only: int      # if uncorroborated, graded penalty instead of kill

class HardKillEvaluator:
    def evaluate(self, headlines: list[Headline], today_candles: pd.DataFrame, symbol: str) -> HardKillVerdict:
        """
        Fires (hard-kill = AVOID) only if at least one of:
        1. ≥2 independent (different domain/source) headlines, both naming symbol with high-confidence entity match.
        2. ≥1 entity-matched headline AND price gap-down on >1.5× delivery-adjusted volume same session.
        3. A structural event class (rating action, exchange filing, regulator action) — provider-verified.
        Otherwise: graded penalty (0–3 points subtracted), no kill.
        """
```

This evaluator runs as part of swing's `EntryGate` (07 §9) and via Monday re-validation (07 §9.4).

---

## 4. Entity resolver (`entity_resolver.py`)

```python
class EntityResolver:
    def resolve(self, headline: Headline, symbol: str) -> EntityMatch:
        """
        Deterministic match using:
        - Exact symbol mention
        - Company name (NSE-listed name, includes aliases like 'L&T' for LARSEN)
        - Avoid false positives via stop-list (e.g., 'TCS' may match Tata Consultancy or Tata Communications; resolver knows which is which based on context tokens).
        Returns EntityMatch(confidence: Literal["high","medium","low","none"]).
        """
```

Only `confidence == "high"` counts for corroboration. Medium/low go into the graded-penalty path.

---

## 5. LLM color (`color.py`)

```python
@dataclass(frozen=True)
class SentimentColor:
    narrative: str        # 2-3 sentences for the dashboard card

class SentimentColorist:
    def narrate(self, headlines: list[Headline], score: SentimentScore) -> SentimentColor:
        """
        Calls OpenRouter through llm/. Returns narrative ONLY.
        The CI rule from 00_principles.md §4 ensures the return value cannot feed scoring.
        """
```

---

## 6. Smart Money — delivery (`shared/smart_money/delivery.py`) — A9 input

```python
@dataclass(frozen=True)
class DeliveryTrendScore:
    score_0_15: int
    delivery_pct_today: float
    delivery_pct_20d_median: float
    trend_slope: float

class DeliveryTrend:
    def compute(self, delivery: pd.DataFrame, today_idx: int) -> DeliveryTrendScore:
        """
        Higher score for:
        - Today's delivery_pct > 20d median by > 5pp
        - 5-session trend slope positive
        Used by swing/pillars (Flow pillar) AND accumulation/pillars (sustained delivery as conviction).
        """
```

---

## 7. Smart Money — bulk/block (`shared/smart_money/bulk_block.py`)

```python
@dataclass(frozen=True)
class BulkBlockScore:
    score_0_15: int
    buyer_class: Literal["FII", "DII", "MF", "INDIVIDUAL", "PROMOTER", "UNKNOWN"]
    net_value_inr: Decimal

class BulkBlockSignal:
    def compute(self, events: list[BulkBlockEvent], lookback_sessions: int = 10) -> BulkBlockScore:
        """
        Higher score for net institutional buying (FII/DII/MF) on bulk deals in last N sessions.
        Promoter selling -> negative.
        """
```

---

## 8. Smart Money — MF accumulation (`shared/smart_money/mf_accumulation.py`) — A7 age decay

```python
@dataclass(frozen=True)
class MFAccumulationVerdict:
    verdict: Literal["ACCUMULATING", "DISTRIBUTING", "NEUTRAL"]
    age_days: int
    confidence_after_decay: float    # 1.0 at 0d, 0.5 at 60d, 0.0 at 120d+ (A7 decay)

class MFAccumulation:
    def evaluate(self, mf_holdings_history: pd.DataFrame, as_of: date) -> MFAccumulationVerdict:
        ...
```

Decay is linear by default; the verdict's effective weight is `score * confidence_after_decay`.

---

## 9. Per-stock flow composer (`shared/smart_money/per_stock_score.py`)

```python
@dataclass(frozen=True)
class FlowScore:
    total_0_15: int
    components: dict[str, int]     # 'delivery', 'bulk_block', 'mf' contributions

class PerStockFlow:
    def compose(self, delivery: DeliveryTrendScore, bb: BulkBlockScore, mf: MFAccumulationVerdict, domain: Literal["swing", "accumulation"]) -> FlowScore:
        """
        Weights differ by domain:
        - swing: delivery 0.5, bulk_block 0.35, mf 0.15
        - accumulation: delivery 0.35, bulk_block 0.20, mf 0.45  (longer horizon values MF accumulation more)
        Total capped at 15.
        """
```

This is the single composer; both `swing/scoring/pillars.py` (Flow pillar) and `accumulation/scoring/pillars.py` (Flow sub-input) call it with `domain` set accordingly.

---

## 10. Tests

### 10.1 `tests/swing/sentiment/`
| Test file | Cases |
|---|---|
| `test_scorer.py` | Positive headlines → positive score. Score capped at 5 (A8 hallmark). |
| `test_scorer_no_llm_input.py` | Static: `scorer.py` does not import from `swing/sentiment/color.py` or `llm/`. (A8) |
| `test_corroboration_two_headlines.py` | Two entity-matched headlines from independent sources → hard-kill fires. |
| `test_corroboration_headline_plus_volume.py` | One entity-matched headline + gap-down on volume → fires. |
| `test_corroboration_structural_event.py` | Rating downgrade → fires. |
| `test_corroboration_uncorroborated.py` | Single keyword match, no other evidence → graded penalty, NOT kill. |
| `test_entity_resolver.py` | TCS context tokens disambiguate Tata Consultancy vs Tata Communications. |
| `test_color_is_color_only.py` | (A8 / C6 hallmark) `SentimentColorist.narrate` return type is `SentimentColor` (text). It has no numeric output. CI rule: AST walk over `swing/scoring/` shows no call into `color.py`. |

### 10.2 `tests/shared/smart_money/`
| Test file | Cases |
|---|---|
| `test_no_fii_dii_in_per_stock.py` | (A7 / C1 hallmark) `grep -r "fii\|dii" src/plutus/shared/smart_money/` is empty. |
| `test_delivery.py` | Score increases monotonically with delivery_pct above median. |
| `test_bulk_block.py` | Net institutional buying → high score. Promoter selling → low. |
| `test_mf_accumulation_decay.py` | At 0 days, full confidence. At 60 days, 0.5. At 120+, 0. |
| `test_per_stock_score_swing_weights.py` | Same inputs, domain=swing → delivery dominates. |
| `test_per_stock_score_accumulation_weights.py` | Same inputs, domain=accumulation → MF dominates. |
| `test_per_stock_score_capped.py` | Max inputs → score = 15, not higher. |

---

## Acceptance criteria

- [ ] FII/DII not consumed in `shared/smart_money/` (CI check).
- [ ] Sentiment max contribution is 5 of 100.
- [ ] Hard-kill requires corroboration; uncorroborated single matches produce graded penalty only.
- [ ] LLM color path produces no numeric output that reaches scoring (CI AST check passes).
- [ ] Same flow composer used by both domains with different weights via `domain` arg.
