# 06 — Shared: Regime & Risk

> Implements A7 (FII/DII relocation), B3 (correlation-aware heat), B4 (drawdown governor), B5 (ADV cap), B13 (breadth + VIX), B15 (cash-as-position), B16 (bounded regime-adaptive allocation).

---

## 1. Module layout

```
src/plutus/shared/regime/
├── __init__.py
├── detector.py          # multi-input regime classifier
├── flip.py              # breadth-confirmed flip logic
└── snapshot.py          # daily persistence helpers

src/plutus/shared/risk/
├── __init__.py
├── portfolio_heat.py    # B3
├── sector_cap.py        # B3
├── correlation_guard.py # B3
├── adv_cap.py           # B5
├── drawdown_governor.py # B4
├── cash_position.py     # B15
└── allocation.py        # B16
```

---

## 2. Regime detector (B13, A7 data side)

```python
@dataclass(frozen=True)
class RegimeInputs:
    nifty_close: Decimal
    nifty_50dma: Decimal
    nifty_200dma: Decimal
    pct_above_50dma: float
    pct_above_200dma: float
    advance_decline: float
    india_vix: float
    fii_flow_5d_sum_inr: Decimal
    dii_flow_5d_sum_inr: Decimal

@dataclass(frozen=True)
class RegimeVerdict:
    label: Literal["BULL", "BEAR", "SIDEWAYS"]
    confidence: Literal["low", "medium", "high"]
    reasons: list[str]
    breadth_confirmed: bool

class RegimeDetector:
    def classify(self, inputs: RegimeInputs) -> RegimeVerdict:
        """
        Deterministic rules:
        - BULL if: nifty > 200DMA AND pct_above_50dma > 0.55 AND vix < settings.vix_bull_max
                   AND 5d FII net > 0
        - BEAR if: nifty < 50DMA AND nifty < 200DMA AND pct_above_200dma < 0.30
                   AND vix > settings.vix_bear_min
        - else SIDEWAYS
        - breadth_confirmed: pct_above_50dma trend over 5d agrees with label
        - confidence by how many rules satisfied (low: 1, medium: 2, high: 3+)
        """
```

FII/DII enters here (relocated from per-stock Smart Money per A7). Never used as a per-stock signal anywhere else.

---

## 3. Flip detection (`regime/flip.py`)

```python
class RegimeFlipDetector:
    def is_flip(self, prior: RegimeVerdict, current: RegimeVerdict) -> bool:
        """True only when label changes AND current.breadth_confirmed."""
```

Used by:
- Scheduler to trigger a re-evaluation of accumulation → swing conversion (bull-ready).
- Allocation to retilt within bounds (B16).

---

## 4. Portfolio heat (B3)

```python
@dataclass(frozen=True)
class HeatInputs:
    open_positions: list[OpenPosition]
    proposed: SwingSignal
    pairwise_correlations: pd.DataFrame  # symbol x symbol, 60d returns

@dataclass(frozen=True)
class HeatDecision:
    allowed: bool
    current_heat_R: float
    projected_heat_R: float
    reasons: list[str]

class PortfolioHeat:
    def evaluate(self, inputs: HeatInputs) -> HeatDecision:
        """
        heat = sum(position.risk_R) with correlation haircut:
          effective_risk_i = risk_i * (1 + mean_correlation_with_others)
        Decision: allowed iff projected_heat_R <= settings.max_portfolio_heat_R.
        """
```

Used as the **last gate** before any swing entry. Rejected proposals go to a "rejected by heat" log on the Postmortem page.

---

## 5. Sector cap (B3)

```python
class SectorCap:
    def check(self, open_positions: list[OpenPosition], proposed: SwingSignal, pool_value_inr: Decimal) -> CapDecision:
        """
        Reject if adding proposed would breach:
          - more than settings.sector_cap_count positions in same sector, OR
          - sector_exposure_pct > settings.sector_cap_pct_of_pool
        """
```

---

## 6. Pairwise correlation guard (B3)

```python
class CorrelationGuard:
    def check(self, open_positions: list[OpenPosition], proposed: SwingSignal, returns_60d: pd.DataFrame) -> GuardDecision:
        """
        Reject if max pairwise correlation (60d returns) between proposed and any open position
        > settings.pairwise_correlation_max.
        """
```

---

## 7. ADV cap (B5)

```python
class ADVCap:
    def max_position_qty(self, symbol: str, price: Decimal, adv_20d_qty: int) -> int:
        return int(adv_20d_qty * self.settings.max_position_pct_of_adv)

    def annotate(self, signal: SwingSignal, qty: int, adv_20d_qty: int) -> str:
        return f"position = {qty / adv_20d_qty:.1%} of 20d ADV"
```

The annotation surfaces on the trade plan card.

---

## 8. Drawdown governor (B4)

```python
class DrawdownGovernor:
    def current_risk_multiplier(self, pool_high_water_mark: Decimal, pool_value: Decimal) -> float:
        """
        Returns 1.0 if drawdown < settings.drawdown_governor_trigger_pct.
        Returns settings.drawdown_governor_halving_factor (0.5) otherwise.
        Restores to 1.0 only after pool recovers above the trigger threshold for 3 consecutive close days.
        """

    def record_close(self, pool_value: Decimal, as_of: date) -> None:
        """Persists daily pool value to compute the 3-day recovery rule."""
```

State stored in `db.DrawdownGovernorState` (single row, upserted).

---

## 9. Cash-as-position (B15)

```python
@dataclass(frozen=True)
class CashDecision:
    deploy_count: int          # how many qualifying signals to deploy
    cash_pct_of_pool: float
    reason: str                # shown on dashboard banner

class CashAsPosition:
    def decide(self, qualifying_signals: list[SwingSignal], pool_value: Decimal) -> CashDecision:
        """
        Rule:
        - If qualifying_signals length < settings.cash_position_min_deploy_count (default 3):
            deploy only the top N by expectancy_R; remainder of pool stays as cash.
        - Banner text: "market offered K qualifying setups; X% of swing pool held in cash."
        """
```

The dashboard's regime banner reads this verbatim.

---

## 10. Allocation (B16)

```python
class Allocation:
    def desired_swing_pct(self, regime: RegimeVerdict) -> float:
        """
        Bull → 0.7, Sideways → 0.5, Bear → 0.3 (clamped within user bounds).
        """

    def reallocate_uncommitted(self, total_capital: Decimal, committed_swing: Decimal, committed_accumulation: Decimal, regime: RegimeVerdict) -> AllocationPlan:
        """
        Only uncommitted capital moves with regime.
        Open swing positions and filled accumulation tranches are never force-migrated.
        Bull-ready remains the voluntary conversion path (08_accumulation_domain.md).
        """
```

---

## 11. Tests

| Test file | Cases |
|---|---|
| `tests/shared/regime/test_detector.py` | Bull-day fixture → BULL with high confidence. Bear-day fixture → BEAR. Mixed → SIDEWAYS. FII positive but breadth negative → confidence drops. |
| `tests/shared/regime/test_flip.py` | Label change without breadth_confirmed → not a flip. With breadth_confirmed → flip. |
| `tests/shared/regime/test_snapshot_round_trip.py` | RegimeVerdict persists to `db.RegimeSnapshot` and re-reads identically. |
| `tests/shared/risk/test_portfolio_heat.py` | Heat without correlation = sum of risks. With pairwise 0.8 correlation → effective heat higher; allowed flips to False at the cap. |
| `tests/shared/risk/test_sector_cap.py` | Exceeding count caps → rejected. Exceeding pct caps → rejected. Diversified portfolio → allowed. |
| `tests/shared/risk/test_correlation_guard.py` | Two highly correlated symbols → reject. Inverse-correlated → allow. |
| `tests/shared/risk/test_adv_cap.py` | qty == 10% of ADV at default settings. Annotation string format correct. |
| `tests/shared/risk/test_drawdown_governor.py` | Below trigger → multiplier 1.0. At trigger → 0.5. 3 days recovery → 1.0. 2 days then dip again → stays 0.5. |
| `tests/shared/risk/test_cash_position.py` | 1 qualifying signal at default min=3 → deploy 1, cash banner text correct. 5 signals → deploy 5, no cash banner. |
| `tests/shared/risk/test_allocation.py` | BULL → swing 70%. Open positions counted as committed; never moved. Uncommitted only retilts. |
| `tests/shared/risk/test_allocation_handoff.py` | Regime flips BULL while accumulation has open tranches → tranches preserved; bull-ready path is the conversion route (cross-ref 08). |

---

## Acceptance criteria

- [ ] FII/DII only consumed by `regime/detector.py`; CI grep verifies no per-stock use.
- [ ] Every swing entry passes through PortfolioHeat → SectorCap → CorrelationGuard → ADVCap before publishing.
- [ ] Drawdown governor halves risk on triggered fixture.
- [ ] Cash-as-position banner string matches the format the dashboard expects.
- [ ] Allocation never force-migrates committed capital.
