# 10 — Backtesting & Benchmarks

> Implements A1 (fill realism), A2 (pooled OOS per-regime shrunk Sharpe), A3 (no per-stock Sharpe in technical pillar), B2 (three benchmarks), B14 (per-regime bundle stat store), and gates the engine-doc PEAD/SMC items (C2, C3) on evidence.

---

## 1. Module layout

```
src/plutus/backtesting/
├── __init__.py
├── runner.py                  # main loop
├── walk_forward.py            # train/OOS windows
├── pooled.py                  # cross-symbol pooled trade stats
├── per_regime.py              # B14
├── shrinkage.py               # shrunk Sharpe
├── selection.py               # bundle selection from stats
└── reports/
    └── benchmark_strip.py     # 3 baselines

src/plutus/shared/benchmarks/
├── __init__.py
├── nifty_buy_hold.py
├── regime_switched.py         # Nifty when BULL, cash when BEAR
└── random_liquid.py           # matched-trade random baseline
```

---

## 2. Runner

```python
@dataclass(frozen=True)
class BacktestConfig:
    start: date
    end: date
    bundles: list[str]
    universe_source: Literal["pit"]       # only PIT allowed (A17)
    use_cost_model: bool = True           # B1 always on by default
    use_fill_policy: bool = True          # A1 always on by default

@dataclass(frozen=True)
class BacktestResult:
    trades: list[BacktestTrade]
    by_bundle: dict[str, BundleStats]
    by_bundle_regime: dict[tuple[str, str], BundleStats]
    benchmarks: BenchmarkResult
    config: BacktestConfig

class BacktestRunner:
    def run(self, cfg: BacktestConfig) -> BacktestResult:
        """
        For each trading day in [start, end]:
          1. PIT universe lookup.
          2. RegimeSnapshot lookup.
          3. For each symbol in universe:
                for each bundle:
                    signal = bundle.fit_signal(...)
                    if signal: schedule open at next bar (A1).
          4. For each open trade: check exits via FillPolicy.
          5. Persist Fills with kind=MOCK, CostBreakdown applied.
        Returns BacktestResult.
        """
```

CI rule: `BacktestRunner.run` may not import from `data/universe.get_live_universe`.

---

## 3. Walk-forward (`walk_forward.py`)

```python
class WalkForward:
    def windows(self, start: date, end: date, train_days: int = 180, oos_days: int = 30, step_days: int = 30) -> Iterator[tuple[Window, Window]]:
        """Yields (train_window, oos_window) tuples, sliding by step_days."""

    def stats(self, trades: list[BacktestTrade], window: Window) -> BundleStats:
        ...
```

---

## 4. Pooled stats (`pooled.py`) — A2

```python
@dataclass(frozen=True)
class BundleStats:
    bundle: str
    regime: str | Literal["ALL"]
    n_trades: int
    win_rate: float
    expectancy_R: float
    sharpe_raw: float
    ci_low_R: float
    ci_high_R: float

class PooledStats:
    def compute(self, trades: list[BacktestTrade], group_by: list[Literal["bundle", "regime"]]) -> dict[tuple, BundleStats]:
        """
        Pool ACROSS the universe per bundle and per (bundle, regime).
        Min n for ranking eligibility: settings.bundle_min_n (default 20).
        Never per-symbol Sharpe (A3): per-symbol stats stay internal to the
        sub-bundle's stop/target sanity test, not exposed to selectors or scorers.
        """
```

---

## 5. Shrinkage (`shrinkage.py`)

```python
def shrunk_sharpe(raw_sharpe: float, n_trades: int, prior_mean: float, prior_weight: float = 30.0) -> float:
    """
    James-Stein-style shrinkage:
      shrinkage = prior_weight / (prior_weight + n_trades)
      result = raw_sharpe * (1 - shrinkage) + prior_mean * shrinkage
    Lower n -> pulled toward prior_mean (cross-bundle mean).
    """
```

---

## 6. Per-regime stat store (`per_regime.py`) — B14

```python
class PerRegimeStatStore:
    def upsert(self, stats: BundleStats, as_of: date, session: Session) -> None:
        """Writes to db.BundleStatPerRegime."""

    def latest(self, bundle: str, regime: str, session: Session) -> BundleStatPerRegime | None:
        ...
```

`swing/scoring/selector.py` reads via this store.

---

## 7. Benchmarks (B2)

### 7.1 `nifty_buy_hold.py`
```python
class NiftyBuyHold:
    def equity_curve(self, start: date, end: date) -> pd.Series: ...
```

### 7.2 `regime_switched.py`
```python
class RegimeSwitched:
    def equity_curve(self, start: date, end: date, regime_history: pd.DataFrame) -> pd.Series:
        """Long Nifty when BULL; cash (no return) otherwise."""
```

### 7.3 `random_liquid.py`
```python
class RandomLiquidBaseline:
    def __init__(self, seed: int = 42): ...

    def matched_trade_curve(self, plutus_trades: list[BacktestTrade], universe_at: Callable[[date], frozenset[str]]) -> pd.Series:
        """
        For each Plutus trade, pick a random PIT-universe symbol with similar liquidity
        AND open a matched-hold-window trade with the same entry day and same hold days.
        Costs applied identically.
        Result: same number of trades, same regimes, same hold windows — no stock-picking skill.
        """
```

### 7.4 Benchmark strip composer

```python
@dataclass(frozen=True)
class BenchmarkResult:
    plutus_net_pct: float
    nifty_net_pct: float
    regime_switched_net_pct: float
    random_liquid_net_pct: float
    plutus_profit_factor: float
    plutus_n_trades: int

class BenchmarkStrip:
    def compute(self, result: BacktestResult) -> BenchmarkResult: ...
```

The Postmortem page consumes this directly.

---

## 8. Tests

### 8.1 `tests/backtesting/`
| Test file | Cases |
|---|---|
| `test_runner_pit_universe.py` | Runner must call `get_universe_at`; calling `get_live_universe` raises (CI). |
| `test_runner_no_same_bar_lookahead.py` | (A1 hallmark) Signal at bar T cannot produce a fill at bar T. |
| `test_runner_costs_applied.py` | Disabling cost model produces visibly higher Sharpe (sanity). Default keeps them on. |
| `test_walk_forward_windows.py` | Train/OOS windows tile without overlap; OOS strictly after train. |
| `test_pooled_no_per_symbol_sharpe.py` | (A3 hallmark) `PooledStats.compute` does not yield per-symbol stat objects to any consumer used by Technical pillar. |
| `test_pooled_min_n_floor.py` | Bundles with n < min_n excluded from ranking. |
| `test_shrinkage.py` | Low n → result close to prior_mean. High n → close to raw. |
| `test_per_regime_store.py` | Upsert idempotent on (bundle, regime, as_of_date). |

### 8.2 `tests/shared/benchmarks/`
| Test file | Cases |
|---|---|
| `test_nifty_buy_hold.py` | Equity curve matches reference fixture. |
| `test_regime_switched.py` | BEAR periods produce flat curve (cash). Compounds during BULL only. |
| `test_random_liquid_matched.py` | Same trade count, same hold windows as Plutus trades. Deterministic with fixed seed. |
| `test_benchmark_strip.py` | All four numbers present and computed net of costs. |
| `test_random_liquid_no_lookahead.py` | Random picks at each trade's day use PIT universe only. |

### 8.3 Integration (`tests/backtesting/integration/`)
| `test_two_quarter_backtest.py` | One year of synthetic data, all four metrics produced, matches manual spot checks. |
| `test_backtest_with_real_fixtures.py` | Uses small parquet fixtures of 5 symbols, 6 months — runs in < 30 seconds. |

---

## Acceptance criteria

- [ ] A1 hallmark green (no same-bar look-ahead).
- [ ] A3 hallmark green (no per-symbol Sharpe in Technical pillar's call graph).
- [ ] Pooled stats computed; per-regime store populated; selector reads from store.
- [ ] All three benchmarks computed every run; postmortem shows the strip.
- [ ] Random baseline deterministic with seed.
- [ ] Two-quarter integration test passes in < 30s.
