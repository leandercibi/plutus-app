# 05 — Cost & Fill Model

> P0. The single change that decides whether any backtest number means anything (review §A1, B1, B10).

---

## 1. Module layout

```
src/plutus/shared/cost_model/
├── __init__.py
├── costs.py             # CostModel
└── slippage.py          # SlippageModel

src/plutus/shared/fills/
├── __init__.py
├── policy.py            # FillPolicy — A1
├── mock_fill.py         # used in backtest / paper
└── real_fill.py         # user-logged actual fills (B10)
```

---

## 2. `CostModel` (B1)

Inputs come from `Settings`. Output is total ₹ cost for one leg of one order.

```python
@dataclass(frozen=True)
class CostBreakdown:
    brokerage: Decimal
    stt: Decimal
    exchange: Decimal
    gst: Decimal
    stamp_duty: Decimal
    total: Decimal

class CostModel:
    def __init__(self, settings: Settings): ...

    def buy_cost(self, qty: int, price: Decimal) -> CostBreakdown:
        notional = qty * price
        brokerage = Decimal(min(self.brokerage_per_order_inr, notional * 0.0003))  # cap at 0.03%
        stt = notional * self.stt_pct                # buy side: STT on delivery
        exchange = notional * self.exchange_pct
        gst = (brokerage + exchange) * self.gst_pct
        stamp_duty = notional * self.stamp_duty_pct
        total = brokerage + stt + exchange + gst + stamp_duty
        return CostBreakdown(...)

    def sell_cost(self, qty: int, price: Decimal) -> CostBreakdown:
        # same structure; STT applies sell-side too on delivery
        ...

    def round_trip_cost(self, qty: int, entry: Decimal, exit: Decimal) -> Decimal:
        return self.buy_cost(qty, entry).total + self.sell_cost(qty, exit).total
```

All Decimal math; no float in cost computation. Test values come from a published broker grid checked into `tests/fixtures/cost_grid.json`.

---

## 3. `SlippageModel`

Slippage scales with **position size relative to ADV** and **stock ATR** (review §B1).

```python
class SlippageModel:
    def __init__(self, settings: Settings): ...

    def slippage_bps(self, qty: int, adv_20d: int, atr_pct: float) -> float:
        """
        bps = base * (1 + position_pct_of_adv * k_size) * (1 + atr_pct * k_vol)
        Calibrated initial constants:
          base = settings.slippage_bps_base = 5.0
          k_size = 10   # 1% of ADV adds ~10% to slippage
          k_vol = 8     # ATR pct ~3% adds ~24% to slippage
        These constants are tuned later via mock-vs-real divergence (B10);
        defaults must produce no negative or zero slippage for any non-trivial input.
        """

    def apply_to_price(self, price: Decimal, side: Literal["BUY", "SELL"], bps: float) -> Decimal:
        # BUY pays more, SELL receives less
        ...
```

---

## 4. `FillPolicy` (A1)

The single rule:

- **Entry:** `next_bar_open + slippage`
- **Stop:** `worse_of(stop_price, next_bar_open) + slippage`
- **Target:** `min(target_price, next_bar_high)` if intra-bar target hit, else `next_bar_open` if gap-through; both with slippage.
- **No same-bar look-ahead.** The signal generated on bar T can only execute on bar T+1.

```python
class FillPolicy:
    def __init__(self, slippage: SlippageModel): ...

    def fill_entry(self, signal: SwingSignal, next_bar: OHLCBar, adv: int, atr_pct: float) -> Fill:
        ...

    def fill_stop(self, trade: SwingTrade, next_bar: OHLCBar, adv: int, atr_pct: float) -> Fill | None:
        """Returns a fill if next_bar.low <= stop OR next_bar.open <= stop;
        price = worse_of(stop, next_bar.open) + slippage on the sell side.
        Returns None if stop not triggered."""

    def fill_target(self, trade: SwingTrade, next_bar: OHLCBar, target_level: int) -> Fill | None:
        """T1 or T2 fills at intra-bar touch; gap-through fills at next_bar.open."""
```

**Gap-through behavior** is the killer detail R2 added: stops fill at the worse of (stop price, next-bar open). This goes verbatim into `fill_stop`.

---

## 5. Mock vs real fills (B10)

```python
def log_real_fill(trade_id: int, side: str, qty: int, price: Decimal, filled_at: datetime, session: Session) -> Fill:
    """User enters actual broker fill via dashboard or API.
    Inserts a Fill with kind='REAL'. Mock fill (if any) is preserved for divergence reporting."""

def slippage_divergence_report(window: timedelta) -> SlippageDivergenceReport:
    """For trades that have BOTH mock and real fills in the window,
    compute mean / median / p90 of (real_price - mock_price) bps.
    Surfaced on Postmortem page; feeds slippage constant re-tuning (E3)."""
```

Calibration (`shared/calibration/`) **prefers REAL fills over MOCK fills** for any trade that has both.

---

## 6. Tests

| Test file | Cases |
|---|---|
| `tests/shared/cost_model/test_costs.py` | Each component matches broker grid fixture to the paisa. Brokerage cap honored at small qty. STT applied both legs. GST on (brokerage + exchange) only. Decimal precision retained. |
| `tests/shared/cost_model/test_slippage.py` | Larger position_pct_of_adv → higher bps (monotonic). Higher atr_pct → higher bps. Zero ADV raises. Negative qty raises. BUY direction increases price; SELL decreases. |
| `tests/shared/fills/test_fill_policy_entry.py` | Entry signal at bar T fills at bar T+1 open + slippage. Property-based: never fills at same-bar prices. |
| `tests/shared/fills/test_fill_policy_stop_normal.py` | Bar T+1 low touches stop, open above stop → fill at stop + slippage. |
| `tests/shared/fills/test_fill_policy_stop_gap.py` | Bar T+1 opens below stop → fill at open + slippage (worse of two). This is the A1 hallmark test; if it fails, fix before anything else. |
| `tests/shared/fills/test_fill_policy_target.py` | Intra-bar T1 fill at target. Gap-up through T2 fills at next open. |
| `tests/shared/fills/test_fill_policy_no_lookahead.py` | Property-based with Hypothesis: any signal at bar T returns no fill before bar T+1. |
| `tests/shared/fills/test_mock_vs_real.py` | Both fill rows coexist for one trade; calibration prefers REAL. |
| `tests/shared/fills/test_slippage_divergence.py` | Report computes mean/median/p90; empty window → empty report (no crash). |
| `tests/shared/cost_model/test_round_trip_meaningful.py` | A 1% drawn-R:R "winner" can become a net loser once costs apply — direct sanity check that the model bites. |

Hypothesis property tests use frozen seeds (`@settings(deterministic=True)`).

---

## 7. Cross-references

- Consumed by `swing/scoring/expectancy.py` (A4) — costs subtracted before expectancy.
- Consumed by `backtesting/runner.py` (A1) — every backtest fill goes through `FillPolicy`.
- Consumed by `swing/exits/*` (B8) for trailing exit fills.
- Persisted in `db.CostModelRun` per run for audit.

---

## Acceptance criteria

- [ ] `CostModel.buy_cost` and `sell_cost` reproduce the broker grid fixture exactly.
- [ ] `FillPolicy.fill_stop` returns the worse of (stop, next_bar.open) on gap-through (hallmark test green).
- [ ] No backtest may produce a `Fill` whose `filled_at` ≤ signal `created_at`.
- [ ] Real fills can be logged and supersede mock fills in calibration queries.
- [ ] Cost+slippage round-trip is wired into A4 expectancy and B2 benchmark comparisons.
