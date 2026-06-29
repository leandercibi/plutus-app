# 11 — Calibration & Tuning

> Implements A14 (SPRT + multiple-testing correction + CIs + regime-conditioned + expectancy objective + opt-in auto-tune), C5 (no win-rate headlines), B17 (soft dead-zone + confidence badges).

The tuning loop's job is to **resist acting**, and to make uncertainty visible when it does.

---

## 1. Module layout

```
src/plutus/shared/calibration/
├── __init__.py
├── lookup.py             # CalibrationLookup — read API for scorers
├── recorder.py           # post-trade outcome ingestion
├── sprt.py               # sequential probability ratio test (A14)
├── ci.py                 # Wilson / bootstrap CIs
├── multiple_testing.py   # Benjamini-Hochberg / Bonferroni helpers
├── regime_partition.py   # bucket per (signal_bucket, regime)
├── deadzone.py           # B17 dead-zone resolution
└── tuner.py              # opt-in auto-tune loop
```

---

## 2. Outcome recorder

```python
@dataclass(frozen=True)
class TradeOutcome:
    trade_id: int
    bundle: str
    regime_at_signal: str
    score_bucket: str            # e.g. "score_70_75"
    realized_R: float            # net of costs; uses REAL fills if present
    horizon_days: int
    closed_at: datetime
    is_paper: bool

class OutcomeRecorder:
    def record(self, outcome: TradeOutcome, session: Session) -> None:
        """
        Appends to outcomes log.
        Updates CalibrationRow for (score_bucket, regime):
          - increments n_closed
          - updates expectancy_R (running mean)
          - recomputes CI via ci.wilson_or_bootstrap
          - advances SPRT state
          - sets confidence_band by n thresholds (low <20, med <50, high >=50)
        """
```

---

## 3. SPRT (`sprt.py`) — A14

```python
class SPRT:
    def __init__(self, alpha: float, beta: float, h0_expectancy: float, h1_expectancy: float): ...

    def update(self, prior_state: SPRTState, new_outcome_R: float) -> SPRTState:
        """
        SPRTState: log-likelihood ratio + decision.
        Tunable thresholds:
          A = log((1 - beta) / alpha)
          B = log(beta / (1 - alpha))
        decision: 'accept_H1' if LLR >= A, 'accept_H0' if LLR <= B, else 'continue'.
        """
```

H0: bundle expectancy ≤ floor (do nothing). H1: > floor by a meaningful margin (act).

---

## 4. Confidence intervals (`ci.py`)

```python
def wilson_interval(successes: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """For binary outcomes (win/loss). Returns (low, high)."""

def bootstrap_R_interval(rs: list[float], conf: float = 0.95, B: int = 5000, seed: int = 0) -> tuple[float, float]:
    """For real-valued realized R."""
```

Seeded; deterministic in tests.

---

## 5. Multiple-testing correction (`multiple_testing.py`)

```python
def benjamini_hochberg(p_values: list[float], q: float = 0.10) -> list[bool]:
    """Returns mask: True where the p-value passes after BH correction."""

def family_size(buckets: int, bundles: int, regimes: int) -> int:
    return buckets * bundles * regimes
```

Used by the tuner: a single bucket flipping significant means nothing until family-corrected.

---

## 6. Regime partition (`regime_partition.py`)

```python
def partition(outcomes: list[TradeOutcome]) -> dict[tuple[str, str], list[TradeOutcome]]:
    """Returns {(bucket, regime): [outcome, ...]}."""
```

Used by `recorder` and by `tuner`.

---

## 7. Calibration lookup (read path for scorers)

```python
class CalibrationLookup:
    def get(self, bundle: str, regime: str, score_bucket: str) -> CalibrationRow | None: ...

    def hit_rate(self, bundle: str, regime: str, target_field: Literal["target_1", "target_2", "stop"]) -> float:
        """Used by composite_geometry and expectancy. Falls back to cross-regime pooled value if n < min_n_low."""

    def confidence_band(self, bundle: str, regime: str, score_bucket: str) -> Literal["low", "medium", "high"]:
        ...
```

---

## 8. Dead-zone (`deadzone.py`) — B17

```python
def is_in_soft_dead_zone(score: int) -> bool:
    return settings.soft_dead_zone_lower <= score <= settings.soft_dead_zone_upper

def deadzone_label(score: int, confidence_band: str) -> Literal["BUY_WATCH", "BUY", "WATCH"]:
    """Used by swing/scoring/classifier.py."""
```

---

## 9. Tuner (`tuner.py`) — A14

```python
@dataclass(frozen=True)
class TunerProposal:
    bundle: str
    regime: str
    parameter: str
    old_value: float
    proposed_value: float
    sprt_state: str
    family_corrected_significant: bool
    expectancy_R_after_change: float
    ci_low_after_change: float
    ci_high_after_change: float
    auto_apply_eligible: bool          # False unless user set settings.auto_tune_enabled = True

class Tuner:
    def propose(self, lookbacks: list[TradeOutcome]) -> list[TunerProposal]:
        """
        Objective: maximize expectancy_R, NOT win rate (A14; C5).
        Rules:
          - Only consider proposals where SPRT accept_H1 AND family-corrected significant.
          - Compute expected expectancy AFTER the change with CIs.
          - Mark auto_apply_eligible only if settings.auto_tune_enabled and CI low > 0.
        Persists proposals; an operator approves before they apply.
        Every applied change is dated and reversible.
        """
```

**Default**: `settings.auto_tune_enabled = False`. The dashboard surfaces proposals; the operator approves.

---

## 10. Tests

| Test file | Cases |
|---|---|
| `tests/shared/calibration/test_recorder.py` | Outcome insert increments n_closed; running expectancy correct; SPRT advances. |
| `tests/shared/calibration/test_sprt_accepts_h1.py` | Stream of +1R outcomes → eventually accept_H1. |
| `tests/shared/calibration/test_sprt_accepts_h0.py` | Stream of −1R outcomes → eventually accept_H0. |
| `tests/shared/calibration/test_sprt_inconclusive.py` | Mixed → stays 'continue'. |
| `tests/shared/calibration/test_ci_wilson.py` | Known values from textbook table reproduced. |
| `tests/shared/calibration/test_ci_bootstrap_seeded.py` | Same inputs + same seed → same interval. |
| `tests/shared/calibration/test_benjamini_hochberg.py` | Standard fixture from Benjamini-Hochberg 1995 reproduced. |
| `tests/shared/calibration/test_regime_partition.py` | Outcomes correctly bucketed by (score_bucket, regime). |
| `tests/shared/calibration/test_lookup_fallback.py` | Bucket with n=5 falls back to cross-regime pooled rate. |
| `tests/shared/calibration/test_deadzone.py` | 67, 70, 73 → True. 66, 74 → False. |
| `tests/shared/calibration/test_tuner_objective_is_expectancy.py` | (A14/C5 hallmark) Given a bucket where higher win-rate variant has LOWER expectancy, tuner does NOT propose it. |
| `tests/shared/calibration/test_tuner_auto_off_by_default.py` | All proposals have `auto_apply_eligible=False` unless config flips. |
| `tests/shared/calibration/test_tuner_family_correction_required.py` | Single uncorrected significant bucket → no proposal. |
| `tests/shared/calibration/test_tuner_manual_override_dated.py` | Applied proposal records timestamp; revert restores prior parameter. |
| `tests/shared/calibration/test_real_fill_preference.py` | Trade with both MOCK and REAL fill → recorder uses REAL R for the outcome. |

---

## Acceptance criteria

- [ ] A14 hallmark test green: tuner optimizes expectancy, not win rate.
- [ ] Auto-tune off by default; CI ensures default config has `auto_tune_enabled=False`.
- [ ] Calibration rows ALWAYS carry CI columns.
- [ ] Dashboard reads `confidence_band` and `ci_low/high` to render badges (cross-ref 14_dashboard.md).
- [ ] Real fills supersede mock fills in outcome computation.
