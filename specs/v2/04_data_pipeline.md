# 04 — Data Pipeline

> Provider-adapter pattern. One adjusted source per symbol per run. Reconcile on overlap. Freshness asserted before any signal publishes. Implements A17, B11, B12, A7 (data side), A9 (delivery feed), B13 (breadth + VIX).

---

## 1. Module layout

```
src/plutus/data/
├── __init__.py
├── base.py                  # OHLCVProvider (Protocol), AdjustmentPolicy
├── ohlcv.py                 # primary + fallback chain
├── delivery.py              # NSE delivery %
├── fii_dii.py
├── vix.py
├── breadth.py               # advance/decline, % above DMAs
├── bulk_block.py
├── earnings_calendar.py
├── news.py                  # NewsAPI adapter; output is text only
├── trading_calendar.py
├── universe.py              # PIT membership snapshots
├── reconciliation.py        # cross-provider overlap checks (B12)
└── freshness.py             # B11
```

---

## 2. Protocols

```python
class OHLCVProvider(Protocol):
    name: str
    adjustment: Literal["adjusted_close_only", "split_adjusted", "split_and_dividend"]

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Returns columns: open, high, low, close, volume, indexed by date."""

class DeliveryProvider(Protocol):
    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Columns: delivery_qty, traded_qty, delivery_pct."""
```

---

## 3. OHLCV chain (`ohlcv.py`)

```python
class OHLCVChain:
    def __init__(self, primary: OHLCVProvider, fallback: OHLCVProvider | None):
        ...

    def fetch(self, symbol: str, start: date, end: date) -> OHLCVResult:
        """One adjusted source per symbol per run (B12).
        - Try primary. On success, ALSO fetch fallback on the LAST 30 trading days
          (overlap window) for reconciliation.
        - Reconcile: if max abs pct-diff on close > 1%, log WARNING with both values
          and tag the result `reconciliation_warning=True`.
        - If primary fails, fallback fully; log INFO with `fallback_used=True`.
        - If both fail, return Result with `success=False`; downstream skips this symbol.
        - Cache to `cache/ohlcv/<symbol>_<lookback>.parquet`; TTL = settings.cache_ttl_ohlcv_hours.
        """
```

**Adjustment policy:** mixing two adjustment conventions in the same series is a P0 bug (review §3.3). The chain only mixes providers across symbols, never within one symbol's series in one run. The result records which provider produced each candle.

**Corporate actions** (split/bonus/dividend): handled by the chosen provider's adjusted feed. The reconciliation step compares ratios across providers; if a split is detected at different dates by primary vs fallback, log CRITICAL and drop the symbol from the run.

---

## 4. Universe (`universe.py`) — A17

```python
@dataclass(frozen=True)
class UniverseSnapshot:
    as_of_date: date
    members: frozenset[str]
    rejected_for_liquidity: frozenset[str]

def build_universe_snapshot(as_of: date) -> UniverseSnapshot:
    """
    Membership rule (deterministic):
    1. Start from seed list (NSE 500 + manual additions in scripts/refresh_seed_universe.py).
    2. Require ≥ settings.universe_min_history_days days of OHLCV available.
    3. Require 20-day median traded value (close * volume) >= settings.universe_liquidity_floor_inr.
    4. Drop suspended / delisted as of `as_of`.
    Persists to db.Universe with one row per (symbol, as_of_date).
    """

def get_universe_at(as_of: date) -> frozenset[str]:
    """Look up the PIT snapshot for backtests. Never recompute on the fly."""
```

Backtests **must** call `get_universe_at(historical_date)`, not the live universe. CI fails any backtest test that imports the live universe.

---

## 5. Delivery (`delivery.py`) — A9

NSE publishes delivery quantity and traded quantity per stock per day with a 1-day lag. Adapter normalizes:

```python
def fetch_delivery(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Columns: delivery_qty, traded_qty, delivery_pct = delivery_qty / traded_qty."""

def delivery_adjusted_volume(traded_qty: pd.Series, delivery_pct: pd.Series) -> pd.Series:
    """Used by swing/bundles/* to replace raw volume in confirmation gates (A9)."""

def is_expiry_or_rebalance_day(d: date) -> bool:
    """F&O monthly expiry / index rebalance dates flagged so volume isn't trusted that day."""
```

---

## 6. Regime inputs (B13, A7 data side)

`fii_dii.py`, `vix.py`, `breadth.py`, `bulk_block.py` each expose:

```python
def fetch_<series>(start: date, end: date) -> pd.Series   # or DataFrame
def latest_<series>() -> <value>
```

Specifically:
- `breadth.fetch_pct_above_dma(window: int)` → series of %  of universe above N-DMA.
- `breadth.fetch_advance_decline()` → daily A/D ratio.
- `vix.fetch_india_vix()` → series.
- `fii_dii.fetch_flows()` → daily net flows in ₹ crore, separate FII and DII columns.
- `bulk_block.fetch(symbol)` → events with `qty`, `value_inr`, `buyer`, `seller`, `date`.

All consumed by `shared/regime/` (FII/DII, VIX, breadth) and `shared/smart_money/` (delivery, bulk/block).

---

## 7. Earnings calendar (`earnings_calendar.py`) — B6

```python
def fetch_earnings_dates(symbol: str, lookahead_days: int = 60) -> list[date]:
    """Best-effort: NSE corporate actions feed; cache 24h."""

def is_earnings_in_window(symbol: str, start: date, end: date) -> bool:
    """Used by swing entry gate (B6) and accumulation thesis re-check (B9)."""
```

If the feed is unavailable for a symbol, treat as "earnings unknown" — swing entries on that symbol get a flag, not a block (the cost of false positives is small).

---

## 8. Trading calendar (`trading_calendar.py`)

```python
def is_trading_day(d: date) -> bool
def last_trading_day(on_or_before: date) -> date
def next_trading_day(on_or_after: date) -> date
def trading_days_between(start: date, end: date) -> list[date]
```

Source: NSE official calendar, hardcoded yearly file + manual additions for unscheduled holidays.

---

## 9. Freshness assertion (`freshness.py`) — B11

```python
def assert_freshness(latest_candle_date: date, run_date: date) -> None:
    """Raises FreshnessError if latest candle != last_trading_day(run_date).
    Called by scheduler before any publish step.
    Honors settings.freshness_assert_enabled (must be True in prod)."""
```

Holiday-shortened weeks: if Monday is a holiday, "last trading day" is the previous Friday. The assertion does not care; it only compares to `last_trading_day(today)`.

---

## 10. Reconciliation (`reconciliation.py`) — B12

```python
class ReconciliationReport:
    symbol: str
    primary_source: str
    fallback_source: str
    max_close_diff_pct: float
    max_volume_diff_pct: float
    split_disagreement: bool
    warnings: list[str]

def reconcile(primary: pd.DataFrame, fallback: pd.DataFrame, window_days: int = 30) -> ReconciliationReport:
    ...
```

Reports persist to `cache/reconciliation/<run_id>.json` for audit.

---

## 11. News (`news.py`)

Adapter only — returns headlines as text. **The deterministic sentiment scorer in `swing/sentiment/` consumes these; the LLM in `llm/` does not receive them in a way that feeds back into scores.** See `09_sentiment_and_smart_money.md`.

```python
@dataclass(frozen=True)
class Headline:
    source: str
    published_at: datetime
    title: str
    body: str
    entities: list[str]      # extracted by deterministic NER, not the LLM

def fetch_headlines(symbol: str, lookback_hours: int = 168) -> list[Headline]:
    ...
```

---

## 12. Tests (`tests/data/`)

| Test file | Cases |
|---|---|
| `test_ohlcv_chain.py` | Primary success + fallback overlap fetched. Primary fail → fallback only, flagged. Both fail → success=False. Cache hit short-circuits. TTL expiry re-fetches. |
| `test_ohlcv_reconciliation.py` | Diff > 1% raises warning flag. Split disagreement raises CRITICAL and drops symbol. |
| `test_delivery.py` | `delivery_pct` clipped to [0, 1]. Missing day → NaN, not zero. `is_expiry_or_rebalance_day` correct for sample dates. |
| `test_universe_pit.py` | Membership at past date matches frozen fixture. `get_universe_at(today)` ≠ `get_universe_at(today - 365 days)`. Liquidity floor in ₹ enforced. |
| `test_universe_backtest_isolation.py` | Backtest code path raises if it tries to access live universe. |
| `test_breadth.py` | `pct_above_dma` ∈ [0, 1]. A/D ratio sign matches contrived fixture. |
| `test_vix.py` | Series monotone in time. Latest value present for last trading day. |
| `test_fii_dii.py` | Flow signs preserved. ₹-crore unit. 5-day rolling sum matches manual calc. |
| `test_bulk_block.py` | Schema, date filtering, qty * value sanity. |
| `test_earnings_calendar.py` | `is_earnings_in_window` true when date in [start, end]. Unknown symbol returns empty list, not error. |
| `test_trading_calendar.py` | Known NSE holidays return False. `last_trading_day(saturday)` = previous Friday. |
| `test_freshness.py` | Equal date → no raise. Off-by-one raises. `freshness_assert_enabled=False` in dev does not raise. In prod, the False config itself is rejected (02_environments_config.md §4). |
| `test_news.py` | Headlines de-duplicated by URL. Empty result on unknown symbol. Entities populated by deterministic NER. |

---

## Acceptance criteria

- [ ] Every module in §1 exists with the API above.
- [ ] All tests in §12 pass.
- [ ] Backtest cannot accidentally use live universe (CI rule).
- [ ] One adjusted source per symbol per run, verified by reconciliation log.
- [ ] Cache TTL honored.
- [ ] Freshness raises before any signal publishes when enabled.
