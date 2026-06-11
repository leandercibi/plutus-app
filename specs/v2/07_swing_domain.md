# 07 — Swing Domain

> The biggest domain. Implements A2 (bundle selection), A3 (technical-pillar circularity break), A4 (expectancy gate), A5 (Composite geometry), A6 (risk single-source), A9 (delivery-adjusted volume), A10 (Technical de-correlation), A11 (Composite default seeding), A14 objective (expectancy not win rate), A15 (Monday re-validation), A16 (cooldown decoupling), B6 (earnings blackout), B7 (circuit awareness), B8 (exit layer), C2 (PEAD gated), C3 (SMC gated).

---

## 1. Module layout

```
src/plutus/swing/
├── __init__.py
├── bundles/
│   ├── base.py             # BaseBundle (ABC)
│   ├── trend.py
│   ├── breakout.py
│   ├── reversal.py
│   ├── vcp.py
│   ├── composite.py        # A5
│   ├── pead.py             # C2 — gated, paper-only until evidence
│   └── smc.py              # C3 — gated, display-only until evidence
├── scoring/
│   ├── pillars.py          # technical, flow, sentiment, regime, expectancy
│   ├── expectancy.py       # A4 — net probability-weighted, after costs
│   ├── composite_geometry.py # A5
│   ├── selector.py         # A2 — pooled OOS per-regime shrunk Sharpe
│   └── classifier.py       # BUY / BUY_WATCH / WATCH / HOLD / AVOID
├── entries/
│   ├── gate.py             # all entry gates in one place
│   ├── volume_gate.py      # A9 — delivery-adjusted
│   ├── circuit_gate.py     # B7
│   ├── earnings_gate.py    # B6
│   └── monday_revalidation.py # A15
├── exits/
│   ├── stop.py
│   ├── trailing.py         # B8 — Chandelier / EMA-trail
│   ├── no_progress.py      # B8 — unified
│   ├── cooldown.py         # A16
│   └── exit_manager.py
├── sizing/
│   └── size.py             # A6 — single source of risk per trade
├── postmortem/
│   └── builder.py
└── sentiment/              # see 09_sentiment_and_smart_money.md
```

---

## 2. `BaseBundle` (ABC)

```python
class BaseBundle(ABC):
    name: ClassVar[str]
    horizon_days: ClassVar[tuple[int, int]]  # (min, max) hold window

    @abstractmethod
    def fit_signal(self, symbol: str, candles: pd.DataFrame, ctx: BundleContext) -> BundleSignal | None:
        """Returns a candidate signal or None (no setup today)."""

    @abstractmethod
    def required_inputs(self) -> set[Literal["ohlcv", "delivery", "bulk_block", "earnings"]]:
        ...
```

`BundleSignal` carries entry, stop, T1, T2, structural reasons, and per-bundle internal score (NOT used for classification — see A3).

---

## 3. Bundles

Each bundle implements `fit_signal`. Acceptance criteria are listed per bundle. **Logic is faithful to the engine doc; only the inputs and outputs change** (delivery-adjusted volume; expectancy gate consumed at scoring time, not in `fit_signal`).

### 3.1 `trend.py`
- Inputs: OHLCV, delivery.
- Setup: 50DMA > 200DMA; price pulled back to 50DMA within 1 ATR; delivery-adjusted volume contraction during pullback.
- Geometry: stop = pullback low − 0.5 ATR; T1 = recent swing high; T2 = 1.5 × (entry − stop) projected up.

### 3.2 `breakout.py`
- Inputs: OHLCV, delivery, bulk/block.
- Setup: Donchian-20 high cleared on bar with delivery-adjusted volume > 1.5× 20-day median.
- **B7 hook**: if symbol hit any circuit band in the last 90 sessions, `CircuitGate` discounts the setup and `fit_signal` returns None unless the breakout is by > 2 ATR (a strong-enough move that circuit truncation is unlikely to be the cause).

### 3.3 `reversal.py`
- Setup: 5 closes below 20DMA, then a bullish engulfing with delivery-adjusted volume confirmation.

### 3.4 `vcp.py`
- Setup: classic Minervini volatility contraction — N contractions of decreasing amplitude on declining volume; breakout from final contraction on expanding delivery-adjusted volume.
- B7: circuit-affected bars excluded from contraction count.

### 3.5 `composite.py` (A5 — geometry repair)
- Aggregates agreeing sub-bundles (any 2+ of trend/breakout/vcp/reversal).
- **Stop = widest structural stop among agreeing sub-bundles** (or median if 3+).
- **T1 = probability-weighted blend of sub-bundle T1s** (weights = historical hit rate per sub-bundle per regime).
- **T2 = probability-weighted blend of sub-bundle T2s.**
- Never tightest-stop + nearest-target. Test enforces this.

### 3.6 `pead.py` — C2 gated
- Runs only when:
  1. `earnings_calendar` confirms a results date in the last 5 sessions for this symbol, AND
  2. Verified-earnings flag set on universe (data quality check passed), AND
  3. `paper_only_pead=True` until one full earnings season with cost model proves net positive.
- Otherwise `fit_signal` returns None.

### 3.7 `smc.py` — C3 gated
- May produce signals but `selector.py` does NOT include SMC in live seeding until pooled OOS per-regime evidence justifies it.
- Default state: display-only (shown on Strategy Lab page; not on Signals page).

---

## 4. Scoring pillars (`scoring/pillars.py`)

Six pillars, total 100:

| Pillar | Weight | Source | Notes |
|---|---|---|---|
| Technical (trend-momentum, collapsed) | 30 | `pillars.technical_score(candles)` | A10 — single sub-score from trend alignment + RSI + MACD treated as one factor; freed weight (was 35) reallocated to ATR percentile and mean-reversion flag. |
| Expectancy (R) | 25 | `expectancy.compute(signal, calibration_lookup, costs)` | A4 — net probability-weighted, after costs. Replaces "R:R drawn." |
| Flow (per-stock) | 15 | `shared/smart_money` — delivery + bulk/block | A7 + A9 |
| Regime fit | 15 | `shared/regime` consumer | |
| Fundamentals (light, swing-side) | 10 | basic D/E + earnings within window flag | hard-avoids only; cannot push score up much |
| Sentiment | 5 | `swing/sentiment/` | A8 — 5% positive, hard-kill requires corroboration |

```python
@dataclass(frozen=True)
class PillarBreakdown:
    technical: int          # 0-30
    expectancy: float       # negative possible
    flow: int               # 0-15
    regime_fit: int         # 0-15
    fundamentals: int       # 0-10
    sentiment: int          # 0-5

class PillarComputer:
    def compute(self, signal: BundleSignal, ctx: SignalContext) -> PillarBreakdown: ...
```

---

## 5. Expectancy gate (`scoring/expectancy.py`) — A4

```python
@dataclass(frozen=True)
class ExpectancyResult:
    expectancy_R: float          # net of costs, after pooled per-regime hit rates
    p_t1: float
    p_t2: float
    p_sl: float
    drawn_rr: float              # kept for fallback floor only
    passes_primary_gate: bool    # expectancy_R >= settings.expectancy_floor_R
    passes_fallback_gate: bool   # drawn_rr >= settings.drawn_rr_fallback_floor when sample small

def compute_expectancy(
    signal: BundleSignal,
    calibration: CalibrationLookup,
    costs: CostModel,
    qty: int,
) -> ExpectancyResult:
    """
    E = p_t1 * R_t1 + p_t2 * R_t2 - p_sl * R_sl
    where R values are AFTER round-trip cost subtraction.
    Hit rates come from CalibrationLookup, conditioned on (bundle, regime).
    Floor: settings.expectancy_floor_R (default +0.3R).
    Fallback floor: settings.drawn_rr_fallback_floor (1.5x) when calibration n < 20.
    """
```

**Drawn R:R is NEVER the primary gate when calibration has ≥ 20 trades.** Test enforces.

---

## 6. Composite geometry (`scoring/composite_geometry.py`) — A5

```python
def widest_stop(sub_signals: list[BundleSignal]) -> Decimal:
    """If 2 sub-signals: the wider of the two stops.
    If 3+: median of stops (closer to widest than tightest)."""

def probability_weighted_target(sub_signals: list[BundleSignal], target_field: Literal["target_1", "target_2"], calibration: CalibrationLookup, regime: str) -> Decimal:
    """weight_i = calibration.hit_rate(bundle_i, regime, target_field)
    target = sum(weight_i * target_i) / sum(weight_i)"""
```

---

## 7. Selector (`scoring/selector.py`) — A2 + A3

```python
@dataclass(frozen=True)
class SelectorInputs:
    pooled_oos_stats: dict[tuple[str, str], BundleStatPerRegime]  # (bundle, regime) -> stat
    min_n: int = 20

class BundleSelector:
    def rank_bundles(self, regime: str, candidates: list[BundleSignal]) -> list[BundleSignal]:
        """
        For each bundle:
          - require n_trades >= settings.bundle_min_n for ranking eligibility
          - rank by walk-forward OOS shrunk Sharpe in current regime
          - shrinkage toward cross-bundle mean ∝ trade count (1/n)
        Default seeding (A11): Composite first if it ranks within the top quartile;
        else single best bundle whose OOS edge is decisively better (Δ ≥ 0.3 in shrunk Sharpe).
        """
```

A3: the **selector** consumes pooled bundle stats. The **Technical pillar** in `pillars.py` consumes raw price/momentum features — it MUST NOT take the per-stock Sharpe as an input. Static-analysis rule in CI: `pillars.py` may not import from `BundleStatPerRegime`.

---

## 8. Classifier (`scoring/classifier.py`)

```python
@dataclass(frozen=True)
class ClassificationOutput:
    label: Literal["BUY", "BUY_WATCH", "WATCH", "HOLD", "AVOID"]
    score: int                      # 0-100
    soft_dead_zone: bool            # B17 — in 67..73 inclusive
    calibration_band: Literal["low", "medium", "high"]
    counterfactual: str             # B17

def classify(score: int, pillar_breakdown: PillarBreakdown, expectancy: ExpectancyResult, calibration: CalibrationLookup) -> ClassificationOutput:
    """
    - AVOID if any hard-avoid pillar fires (cooldown, hard-kill sentiment, expectancy_R < 0).
    - HOLD if expectancy fails primary gate AND fallback gate.
    - WATCH if score < 67.
    - BUY_WATCH if 67 <= score <= 73 (soft dead zone B17).
    - BUY if score > 73 AND expectancy gate passes.
    - Counterfactual: nearest single-input change that flips BUY_WATCH↔BUY, or moves AVOID→HOLD.
    """
```

---

## 9. Entry gates (`entries/gate.py`)

```python
class EntryGate:
    def __init__(self, volume: VolumeGate, circuit: CircuitGate, earnings: EarningsGate, monday_reval: MondayRevalidation, heat: PortfolioHeat, sector: SectorCap, corr: CorrelationGuard, adv: ADVCap, cooldown: AlertCooldown): ...

    def evaluate(self, signal: SwingSignal, ctx: EntryContext) -> EntryDecision:
        """
        Order matters:
        1. CircuitGate (B7)
        2. EarningsGate (B6) — may downgrade or widen stop, not kill outright
        3. VolumeGate (A9) — delivery-adjusted
        4. PortfolioHeat (B3, shared)
        5. SectorCap (B3)
        6. CorrelationGuard (B3)
        7. ADVCap (B5)
        8. Cooldown (A16)
        Returns EntryDecision(allowed=bool, reasons=[...], adjusted_signal=...).
        """
```

### 9.1 `volume_gate.py` (A9)
```python
class VolumeGate:
    def passes(self, candles: pd.DataFrame, delivery: pd.DataFrame, today_idx: int) -> bool:
        """Delivery-adjusted volume on the confirmation candle > 1.3× 20-day median delivery-adjusted volume.
        Skips if today is an expiry/rebalance day (delivery.is_expiry_or_rebalance_day)."""
```

### 9.2 `circuit_gate.py` (B7)
```python
class CircuitGate:
    def status(self, symbol: str, candles: pd.DataFrame, lookback_sessions: int = 90) -> CircuitStatus:
        """Returns hit count, last hit date, suppression recommendation."""
```

### 9.3 `earnings_gate.py` (B6)
```python
class EarningsGate:
    def evaluate(self, signal: BundleSignal) -> EarningsAdjustment:
        """If earnings date inside hold window:
           - Downgrade signal one band (BUY → BUY_WATCH), OR
           - Widen stop by 1 ATR (configurable).
           Both options recorded; the configured policy decides."""
```

### 9.4 `monday_revalidation.py` (A15)
```python
class MondayRevalidation:
    def reevaluate(self, sunday_signal: SwingSignal, monday_open: Decimal, monday_premarket_news: list[Headline]) -> RevalidationOutcome:
        """Re-runs entry gates with Monday's open as the new entry baseline.
        Weekend gap > 1 ATR -> kill (the trade plan was for the old entry).
        Sentiment hard-kill triggered by weekend news -> kill.
        Otherwise pass through; outcome logged."""
```

---

## 10. Exits (`exits/`)

### 10.1 `stop.py`
Simple SL hit detection; delegates fill mechanics to `shared/fills/policy.py`.

### 10.2 `trailing.py` (B8)
```python
class ChandelierTrail:
    def trail_stop(self, candles: pd.DataFrame, entry_idx: int, current_idx: int, n_atr: float, atr_period: int) -> Decimal:
        return highest_high_since_entry - n_atr * atr

class EMATrail:
    def trail_stop(self, candles: pd.DataFrame, ema_period: int) -> Decimal:
        return ema_value
```

Parameters chosen by `postmortem.builder` from collected MFE/MAE data (review §B8). Backtested like any bundle rule.

### 10.3 `no_progress.py` (B8 — unified)
```python
class NoProgressExit:
    def should_exit(self, trade: SwingTrade, candles: pd.DataFrame, today: date) -> bool:
        """
        If realized R toward T1 < settings.no_progress_t1_threshold (e.g., 0.3)
        by elapsed_pct >= settings.no_progress_elapsed_threshold (e.g., 0.5) of hold window
        → exit at market (scratched).
        Subsumes R1's early-window gap and R2's midpoint rule into one.
        """
```

### 10.4 `cooldown.py` (A16)
```python
class CooldownPolicy:
    def can_fire(self, symbol: str, kind: Literal["SL_BREACH", "SL_WARNING", "T1_HIT", "NO_PROGRESS"], now: datetime, session: Session) -> bool:
        """
        SL_BREACH: NEVER suppressed by any cooldown. Always fires.
        Other kinds: 1-hour cooldown per kind, per symbol — independent of each other.
        """
```

### 10.5 `exit_manager.py`
Owns the daily exit-check loop. Reads open trades, applies (stop → trailing → no_progress), emits exit alerts via `alerts/`, persists fills.

---

## 11. Sizing (`sizing/size.py`) — A6

```python
class PositionSizer:
    def compute_qty(self, signal: SwingSignal, pool_value: Decimal, atr: Decimal, adv_20d: int, governor_multiplier: float) -> int:
        risk_per_trade_inr = pool_value * settings.risk_per_trade_pct * governor_multiplier
        risk_per_share = signal.entry - signal.stop_loss
        qty_by_risk = risk_per_trade_inr / risk_per_share
        qty_by_adv = adv_20d * settings.max_position_pct_of_adv
        return int(min(qty_by_risk, qty_by_adv))
```

`settings.risk_per_trade_pct` is the ONLY source of per-trade risk in swing code. CI lint rule: no other constant in this range can multiply pool value.

---

## 12. Postmortem builder (`postmortem/builder.py`)

Produces the weekly Markdown report with:
- Realized expectancy vs forecast expectancy.
- Bucket calibration tables with CIs.
- Slippage divergence (mock vs real).
- Bundle pull-throughs per regime.
- WRONG_DIRECTION counts.
- Net vs three benchmarks (B2).

Output is consumed by the dashboard Postmortem window.

---

## 13. Tests (per class, per method)

Organized by module. Each test file mirrors the source path.

### 13.1 `tests/swing/bundles/`
| Test file | Cases |
|---|---|
| `test_base.py` | `BaseBundle` cannot be instantiated; subclass missing `fit_signal` errors at construction. |
| `test_trend.py` | Fixture A (clean trend pullback) → signal with stop below pullback low. Fixture B (no pullback) → None. Fixture C (downtrend) → None. |
| `test_breakout.py` | Donchian-20 break with volume → signal. Without volume → None. Circuit-hit fixture → None unless break > 2 ATR. |
| `test_reversal.py` | Engulfing after 5 down closes → signal. Engulfing without delivery confirmation → None. |
| `test_vcp.py` | Three contractions then breakout → signal. Circuit-affected bars excluded from contraction count. |
| `test_composite.py` | Two agreeing sub-bundles → stop = widest of two (A5 hallmark). One sub-bundle → no composite. Three → median stop. Probability-weighted target matches manual calc. |
| `test_composite_a5_hallmark.py` | Construct a fixture where tightest-stop+nearest-target gives 1.33R and widest+prob-weighted gives 1.7R → composite returns 1.7R variant. If this fails, fix before anything else. |
| `test_pead.py` | No earnings in last 5 sessions → None. With earnings + paper_only flag → signal flagged paper_only. |
| `test_smc.py` | Returns signal but `selector.rank_bundles` excludes it from live seeding by default. |

### 13.2 `tests/swing/scoring/`
| Test file | Cases |
|---|---|
| `test_pillars_technical.py` | Single trend-momentum sub-score (A10): trend + RSI + MACD collapse; sum bounded 0–30. ATR percentile and mean-reversion flag contribute. |
| `test_pillars_no_per_stock_sharpe_leak.py` | Static: `pillars.py` does not import `BundleStatPerRegime`. (A3) |
| `test_expectancy_primary_gate.py` | Trend setup with 60% T1 hit, 1.5× drawn but +0.42R net → passes. 25% T1 hit, 2.2× drawn but −0.05R net → fails. |
| `test_expectancy_fallback_gate.py` | Calibration n < 20 → fallback to 1.5× drawn floor; passes/fails accordingly. |
| `test_expectancy_after_costs.py` | Switching cost model off vs on changes the gate verdict on a marginal setup. |
| `test_composite_geometry.py` | `widest_stop` and `probability_weighted_target` correct on synthetic inputs. |
| `test_selector_ranks_by_oos_per_regime_shrunk_sharpe.py` | Stat table with one bundle's BULL Sharpe high — selector ranks it first in BULL regime, not in BEAR. |
| `test_selector_default_composite_seed.py` | Composite top-quartile → selected. Composite mid + single bundle Δ ≥ 0.3 → single bundle. (A11) |
| `test_classifier_bands.py` | Score 70 → BUY_WATCH. Score 76 + expectancy pass → BUY. Score 65 → WATCH. Hard-kill → AVOID. |
| `test_classifier_counterfactual.py` | BUY_WATCH at 70 returns string naming the single input change that would flip it. |

### 13.3 `tests/swing/entries/`
| `test_volume_gate.py` | Delivery-adjusted >1.3× → pass. Expiry day → skipped (returns true unconditionally — gate not applied). |
| `test_circuit_gate.py` | One 5% hit 30 days ago → suppression recommended. No hits → no suppression. |
| `test_earnings_gate.py` | Date inside hold window → downgrade or widen stop. Outside → pass-through. |
| `test_monday_revalidation.py` | Weekend gap > 1 ATR → kill. Hard-kill sentiment → kill. Clean Monday → pass. |
| `test_entry_gate_order.py` | Gates run in §9 order. Circuit failure short-circuits before heat. |

### 13.4 `tests/swing/exits/`
| `test_stop.py` | SL hit returns Fill via FillPolicy. |
| `test_chandelier_trail.py` | Trail tightens as new highs print. |
| `test_ema_trail.py` | Stop tracks EMA. |
| `test_no_progress.py` | Below threshold at midpoint → exit. Above → hold. |
| `test_cooldown_decoupled.py` | (A16 hallmark) Fire SL_WARNING then attempt SL_BREACH within 1 hour → BREACH still fires immediately. |
| `test_exit_manager_priority.py` | Stop wins over no_progress on same bar. |

### 13.5 `tests/swing/sizing/`
| `test_size_risk_per_trade.py` | qty = pool * risk_per_trade_pct / risk_per_share at default settings. |
| `test_size_adv_cap_bites.py` | Big position is clipped by ADV cap, not risk cap. |
| `test_size_drawdown_governor.py` | Governor multiplier halves qty on triggered state. |
| `test_size_only_one_risk_constant.py` | (A6 hallmark) AST/grep scan: no other constant in `swing/sizing/` multiplies pool by 0.01–0.05. |

### 13.6 `tests/swing/postmortem/`
| `test_builder_renders.py` | Sample run → Markdown contains all required sections. |
| `test_postmortem_shows_three_benchmarks.py` | B2 — all three baselines present. |
| `test_postmortem_calibration_with_cis.py` | CI columns present beside every win rate / expectancy figure. |

---

## Acceptance criteria

- [ ] Every class and method in §2–§12 exists.
- [ ] Every test file in §13 exists and passes.
- [ ] A3 import check passes: `pillars.py` does not import `BundleStatPerRegime`.
- [ ] A5 hallmark test passes (`test_composite_a5_hallmark.py`).
- [ ] A6 hallmark test passes (`test_size_only_one_risk_constant.py`).
- [ ] A16 hallmark test passes (`test_cooldown_decoupled.py`).
- [ ] Static check passes: `swing/` does not import `accumulation/`.
- [ ] Static check passes: `swing/` does not import `llm/` from any code path reaching `classifier.py`, `expectancy.py`, `pillars.py`, `selector.py`.
