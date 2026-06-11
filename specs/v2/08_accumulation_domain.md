# 08 — Accumulation Domain

> Implements A12 (fundamentals fix), A13 (ATR-normalized tranches + thesis re-check), B9 (thesis-invalidation exit), bull-ready voluntary conversion. The "patient capital" side.

---

## 1. Module layout

```
src/plutus/accumulation/
├── __init__.py
├── fundamentals/
│   ├── scoring.py            # pillar weights, valuation cap 30% (A12)
│   ├── valuation.py          # multi-year CAGR, normalized earnings (A12)
│   ├── quality.py            # ROCE, D/E, FCF
│   └── hard_avoid.py         # D/E breach, earnings collapse triggers
├── rs/
│   └── blend.py              # 30/90/180-day RS blend (A12)
├── tranches/
│   ├── plan.py               # 5 tranches per position
│   ├── triggers.py           # ATR-normalized (A13)
│   └── revalidation.py       # per-tranche thesis re-check (A13)
├── exits/
│   └── thesis_invalidation.py  # B9
├── bull_ready/
│   └── converter.py          # voluntary conversion to swing
├── scoring/
│   ├── pillars.py
│   └── classifier.py
└── postmortem/
    └── builder.py
```

---

## 2. Pillars (`scoring/pillars.py`)

| Pillar | Weight | Source | Notes |
|---|---|---|---|
| Quality | 30 | `quality.score(...)` | ROCE, D/E, FCF margins |
| Growth | 25 | `valuation.growth_score(...)` | Multi-year CAGR, NOT YoY EPS (A12) |
| Valuation | ≤30 capped | `valuation.score(...)` | Cap is hard (A12) — cannot exceed 30 of 100 |
| Relative Strength | 15 | `rs/blend.py` | 30/90/180-day blend |

Sentiment is **not** an accumulation pillar (decision in 09; accumulation thesis-break is fundamentals-driven via B9).

---

## 3. Fundamentals

### 3.1 `valuation.py` (A12)

```python
@dataclass(frozen=True)
class ValuationInputs:
    pe_ttm: float
    pe_5y_median: float
    ev_ebitda: float
    earnings_history_5y: pd.DataFrame   # columns: year, eps

class Valuation:
    def normalized_eps(self, history: pd.DataFrame) -> float:
        """
        Average EPS over last 5 fiscal years to dampen base-effect (R2's catch).
        Excludes any year with eps < 0 from normalization base; flagged separately.
        """

    def cagr_eps(self, history: pd.DataFrame, years: int = 5) -> float | None:
        """CAGR over `years`; None if any negative endpoint or insufficient history."""

    def score(self, inputs: ValuationInputs) -> int:
        """
        Out of 30 max (capped — A12).
        Cheap PE relative to 5y median is good; cheap because cyclical (CAGR ≤ 0) is NOT.
        Mechanically capped: even a screaming-cheap value-trap scores ≤ 30.
        """

    def growth_score(self, history: pd.DataFrame) -> int:
        """
        Out of 25.
        Uses 3y and 5y CAGR (not YoY) per A12. Penalizes single-year base-effect spikes.
        """
```

### 3.2 `quality.py`

```python
class Quality:
    def score(self, roce: float, de: float, fcf_margin: float) -> int:
        """Out of 30. Higher ROCE good, lower D/E good, positive FCF margin good."""
```

### 3.3 `hard_avoid.py`

```python
@dataclass(frozen=True)
class HardAvoidResult:
    avoid: bool
    reasons: list[str]

class HardAvoid:
    def evaluate(self, fundamentals: FundamentalsSnapshot) -> HardAvoidResult:
        """
        Fires when:
          - D/E > settings.accumulation_de_max (default 1.5), AND not a financial
          - Last reported EPS collapse > 50% YoY with no improving guidance
          - Going-concern audit flag
          - Promoter pledge increase > 10pp in last quarter
        """
```

Evaluated at initial scoring AND at every re-score AND at every tranche entry (B9).

---

## 4. Relative strength blend (`rs/blend.py`) — A12

```python
class RSBlend:
    def compute(self, candles: pd.DataFrame, nifty_candles: pd.DataFrame) -> RSBlendResult:
        """
        rs_30 = (stock_return_30 - nifty_return_30)
        rs_90 = ... (90d)
        rs_180 = ... (180d)
        blended = 0.2*rs_30 + 0.4*rs_90 + 0.4*rs_180     # heavier on longer horizons (A12)
        """
```

---

## 5. Tranche plan (`tranches/`)

### 5.1 `plan.py`

```python
@dataclass(frozen=True)
class TranchePlan:
    n_tranches: int = 5
    base_qty: int                   # per tranche
    seed_price: Decimal             # initial entry

class TranchePlanner:
    def make_plan(self, signal: AccumulationCandidate, pool_value: Decimal) -> TranchePlan:
        ...
```

### 5.2 `triggers.py` (A13)

```python
class ATRNormalizedTrigger:
    def next_trigger_price(self, last_filled_price: Decimal, atr_pct: float, tranche_seq: int) -> Decimal:
        """
        Trigger drop = k_seq * atr_pct, NOT fixed -8% / -15%.
        k_seq schedule: tranche 2 at 1.5 ATR, tranche 3 at 2.5 ATR, tranche 4 at 3.5 ATR, tranche 5 at 5 ATR.
        Result: FMCG (low ATR) tranches more closely spaced in % terms;
        high-beta smallcap (high ATR) tranches widely spaced — same conviction structure.
        """
```

### 5.3 `revalidation.py` (A13)

```python
class TrancheRevalidator:
    def revalidate(self, position: AccumulationPosition, latest_fundamentals: FundamentalsSnapshot) -> RevalidationOutcome:
        """
        Before averaging down (any tranche after the first), the thesis must be re-verified:
          - HardAvoid does not fire
          - Quality pillar score has not dropped > 10 points since last tranche
          - No earnings collapse in the latest filing
        If revalidation fails: the position is PAUSED. No more tranches deploy.
        Operator can manually un-pause after review.
        """
```

---

## 6. Thesis-invalidation exit (`exits/thesis_invalidation.py`) — B9

```python
class ThesisInvalidationExit:
    def evaluate(self, position: AccumulationPosition, latest_fundamentals: FundamentalsSnapshot) -> ExitDecision:
        """
        Re-runs HardAvoid on EVERY re-score (weekly).
        If a hard-avoid condition fires post-entry:
          - Emit EXIT alert via alerts/ (even at a loss)
          - State -> EXITED
        Accumulation no longer has the 'hold through anything' default (R1's catch).
        """
```

Cross-reference: `07_swing_domain.md` does NOT depend on this. Accumulation exits are independent.

---

## 7. Bull-ready voluntary conversion (`bull_ready/converter.py`)

```python
class BullReadyConverter:
    def evaluate(self, position: AccumulationPosition, regime: RegimeVerdict, technicals: SwingSignal | None) -> ConversionOutcome:
        """
        When regime flips BULL with breadth_confirmed AND a swing setup forms on the position's symbol,
        offer to CONVERT the accumulation position into a swing tracked position.
        This is the only mechanism by which capital crosses domains (08 design principle).
        Voluntary: operator confirms; auto-convert is off by default (B16 constraint).
        """
```

State transition: `AccumulationPosition.state = CONVERTED_TO_SWING`; a new `SwingTrade` opens with the average cost as the effective entry for reporting purposes (but stop/targets are set fresh by the swing plan).

---

## 8. Classifier (`scoring/classifier.py`)

```python
class AccumulationClassifier:
    def classify(self, pillar_score: int, hard_avoid: HardAvoidResult) -> AccumulationLabel:
        """
        labels: ACCUMULATE_NOW, BUILD_SLOWLY, WATCH, AVOID
        - AVOID if hard_avoid.avoid
        - WATCH if score < 60
        - BUILD_SLOWLY if 60 <= score < 75
        - ACCUMULATE_NOW if score >= 75 and quality pillar >= 22
        """
```

---

## 9. Postmortem builder

Weekly accumulation postmortem: position-by-position thesis status, RS blend movement, tranche fill summary, paused list with reasons. Renders to `reports/weekly/<date>.md` alongside swing postmortem.

---

## 10. Tests (`tests/accumulation/`)

| Test file | Cases |
|---|---|
| `fundamentals/test_valuation.py` | `normalized_eps` excludes negative years. `cagr_eps` returns None on insufficient history. PE cheap + CAGR negative → value-trap → low score. PE cheap + CAGR strong → high score. |
| `fundamentals/test_valuation_cap.py` | (A12 hallmark) No combination of valuation inputs produces a score > 30. |
| `fundamentals/test_valuation_growth_uses_cagr_not_yoy.py` | (A12 hallmark) Recovery year +120% YoY EPS does NOT spike growth_score; CAGR-based score is moderate. |
| `fundamentals/test_quality.py` | High ROCE / low D/E / positive FCF → max score. |
| `fundamentals/test_hard_avoid.py` | D/E breach → fires. EPS collapse → fires. Non-financial vs financial D/E rule respected. |
| `rs/test_blend.py` | Weight schedule (0.2/0.4/0.4) verified. Short-horizon noise doesn't dominate blended. |
| `tranches/test_plan.py` | Five tranches sized from pool_value. |
| `tranches/test_triggers.py` | (A13 hallmark) Low-ATR fixture and high-ATR fixture produce different absolute % drops for the same `seq`. Triggers always wider for higher ATR. |
| `tranches/test_revalidation.py` | (A13 hallmark) Quality drop > 10 points between tranche 2 and 3 → revalidation FAIL → position PAUSED. |
| `tranches/test_revalidation_pass_through.py` | Stable fundamentals → revalidation passes; next tranche may fire. |
| `exits/test_thesis_invalidation.py` | (B9 hallmark) Position open, then a hard-avoid condition fires on re-score → EXIT decision emitted. |
| `bull_ready/test_converter.py` | Bull regime + breadth + swing setup → conversion offered. Without breadth → no offer. |
| `bull_ready/test_converter_auto_off_by_default.py` | Auto-convert OFF; operator action required. |
| `scoring/test_classifier.py` | Each label condition. Hard_avoid → AVOID regardless of score. |
| `postmortem/test_builder.py` | Renders required sections including PAUSED list. |
| `test_isolation_from_swing.py` | (Architectural) AST scan: `accumulation/` does not import from `swing/`. |

---

## Acceptance criteria

- [ ] All A12 / A13 / B9 hallmark tests pass.
- [ ] Valuation cap test green (no inputs produce > 30).
- [ ] Tranche triggers ATR-normalized, not fixed.
- [ ] Thesis-invalidation exit emits a real alert (cross-tested with `tests/alerts/`).
- [ ] Bull-ready conversion is voluntary; no auto-conversion path exists in default config.
- [ ] `accumulation/` does not import from `swing/`; CI check.
