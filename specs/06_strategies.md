# 06 — Trading Strategy Bundles (Backtrader)

> **5 peer strategy bundles.** All five run independently as their own
> `bt.Strategy` subclasses inside Cerebro. Each one is a peer — Composite is
> not a meta-filter; it is a fifth Backtrader strategy whose internal entry
> rule is "at least 3 of the other 4 bundles agree on this same bar."
>
> Backtrader documentation: https://www.backtrader.com/docu/

---

## Bundle Roster

| # | Bundle | Module | Class | Idea |
|---|---|---|---|---|
| 1 | Trend     | `plutus.strategies.bundle_trend`     | `TrendBundle`     | EMA9>EMA21, RSI 50–72, volume confirmation, ADX>20 |
| 2 | Reversal  | `plutus.strategies.bundle_reversal`  | `ReversalBundle`  | Lower-BB tag + RSI<35 + MACD turning up in low-ADX regime |
| 3 | Breakout  | `plutus.strategies.bundle_breakout`  | `BreakoutBundle`  | Close above N-day high after ATR compression + 2× volume surge |
| 4 | SMC       | `plutus.strategies.bundle_smc`       | `SMCBundle`       | Liquidity grab / Order Block / Fair Value Gap reclaim |
| 5 | Composite | `plutus.strategies.bundle_composite` | `CompositeBundle` | Long only when ≥3 of bundles 1–4 report a long signal on the SAME bar |

Module path everywhere is `plutus.strategies.<bundle_X>`. Imports inside this
package use `from plutus.strategies.base import BaseStrategy`.

---

## Key Backtrader Concepts

```
bt.Strategy          — base class for all strategies
bt.indicators        — built-in indicator library
self.data            — default data feed (OHLCV)
self.broker          — order execution + cash/position tracking
self.buy() / sell()  — place market orders
self.close()         — close current position
self.position        — current open position (size, price)
Cerebro              — backtesting engine; add strategy + data + run
```

---

## `src/plutus/strategies/base.py`

Shared base class. Provides:
- A canonical parameter pair (`risk_pct`, `rr_ratio`) used by every bundle's
  position sizing and target math.
- A `calc_position_size(entry, stop) -> int` helper that risks `risk_pct` of
  current cash per trade, capped at 25% of cash deployed in any single trade.
- A `has_long_signal() -> bool` stub. Bundles 1–4 override it. Composite calls
  into all four.

```python
# src/plutus/strategies/base.py
import backtrader as bt


class BaseStrategy(bt.Strategy):
    """
    Shared base for all 5 bundles.

    Subclasses MUST override:
        has_long_signal(self) -> bool      — pure indicator read; no order/position state
        next(self)                         — entry / exit plumbing using has_long_signal()
    """
    params = (
        ("risk_pct", 5.0),     # % of cash to risk per trade
        ("rr_ratio", 2.0),     # reward-to-risk multiple used to derive target from stop
    )

    def __init__(self):
        self.order = None
        self.entry_price = None
        self.stop_price = None
        self.target_price = None
        self.trade_log = []

        # Indicators that every bundle relies on. Subclass __init__ adds its own.
        self.atr = bt.indicators.ATR(self.data, period=14)

    # ------------------------------------------------------------------ #
    # Signal API
    # ------------------------------------------------------------------ #
    def has_long_signal(self) -> bool:
        """Return True if conditions for a long entry hold on the current bar.

        Default is False; bundles 1–4 override. Composite aggregates the four.
        """
        return False

    # ------------------------------------------------------------------ #
    # Sizing
    # ------------------------------------------------------------------ #
    def calc_position_size(self, entry: float, stop: float) -> int:
        """Risk-based position sizing.

        Risk per trade = (risk_pct/100) × current_cash.
        Shares = floor(risk_per_trade / per_share_risk).
        Hard cap: never deploy more than 25% of cash on a single trade.
        """
        per_share_risk = abs(entry - stop)
        if per_share_risk <= 0 or entry <= 0:
            return 0
        cash = self.broker.getcash()
        risk_budget = cash * (self.p.risk_pct / 100.0)
        shares_by_risk = int(risk_budget // per_share_risk)
        shares_by_cap = int((cash * 0.25) // entry)
        return max(0, min(shares_by_risk, shares_by_cap))

    # ------------------------------------------------------------------ #
    # Order / trade plumbing
    # ------------------------------------------------------------------ #
    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.entry_price = order.executed.price
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        size = trade.size or 1
        self.trade_log.append({
            "pnl": round(trade.pnl, 2),
            "pnl_pct": round((trade.pnl / (trade.price * abs(size))) * 100, 2),
            "entry": round(trade.price, 2),
            "exit": round(trade.price + trade.pnl / size, 2),
            "size": size,
            "bars_held": trade.barlen,
        })
```

---

## Bundle 1 — Trend (`src/plutus/strategies/bundle_trend.py`)

**Description.** EMA-crossover trend follower. Enters long when fast EMA crosses
above slow EMA while price sits above the 50-EMA, RSI is in the bullish-but-not-
overbought band, volume confirms, and ADX shows directional strength.

**Indicators / patterns.** EMA9, EMA21, EMA50, RSI(14), ADX(14), 20-day volume SMA.

**Best market regime.** Trending markets — ADX > 20, price persistently above
the 50-EMA. Underperforms in chop.

```python
# src/plutus/strategies/bundle_trend.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class TrendBundle(BaseStrategy):
    """Bundle 1 — EMA crossover trend follower."""

    params = (
        ("ema_fast", 9),
        ("ema_slow", 21),
        ("ema_filter", 50),
        ("rsi_min", 50),
        ("rsi_max", 72),
        ("adx_min", 20),
        ("vol_min_ratio", 1.5),
    )

    def __init__(self):
        super().__init__()
        self.ema_fast = bt.indicators.EMA(self.data.close, period=self.p.ema_fast)
        self.ema_slow = bt.indicators.EMA(self.data.close, period=self.p.ema_slow)
        self.ema_filter = bt.indicators.EMA(self.data.close, period=self.p.ema_filter)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.adx = bt.indicators.AverageDirectionalMovementIndex(self.data, period=14)
        self.vol_ma = bt.indicators.SMA(self.data.volume, period=20)

    def has_long_signal(self) -> bool:
        if len(self.data) < self.p.ema_filter + 2:
            return False
        cross_up = self.ema_fast[0] > self.ema_slow[0] and self.ema_fast[-1] <= self.ema_slow[-1]
        above_filter = self.data.close[0] > self.ema_filter[0]
        rsi_ok = self.p.rsi_min < self.rsi[0] < self.p.rsi_max
        vol_ok = self.vol_ma[0] > 0 and self.data.volume[0] > self.p.vol_min_ratio * self.vol_ma[0]
        adx_ok = self.adx.adx[0] > self.p.adx_min
        return cross_up and above_filter and rsi_ok and vol_ok and adx_ok

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.has_long_signal():
                entry = self.data.close[0]
                stop = min(self.ema_slow[0], entry - 2 * self.atr[0])
                if stop >= entry:
                    return
                target = entry + self.p.rr_ratio * (entry - stop)
                size = self.calc_position_size(entry, stop)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.stop_price = stop
                    self.target_price = target
        else:
            ema_cross_down = self.ema_fast[0] < self.ema_slow[0]
            if (
                self.data.close[0] <= self.stop_price
                or self.data.close[0] >= self.target_price
                or ema_cross_down
            ):
                self.order = self.close()
```

---

## Bundle 2 — Reversal (`src/plutus/strategies/bundle_reversal.py`)

**Description.** Bollinger-band mean-reversion. Long when price tags or pierces
the lower band while RSI is oversold and MACD histogram is curling up — a
classic exhaustion-then-rebound setup.

**Indicators / patterns.** Bollinger Bands(20,2), RSI(14), MACD(12,26,9), ADX(14).

**Best market regime.** Low-ADX ranging / sideways markets. Targets the middle
band as the mean.

```python
# src/plutus/strategies/bundle_reversal.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class ReversalBundle(BaseStrategy):
    """Bundle 2 — Bollinger band mean reversion with RSI + MACD confirmation."""

    params = (
        ("rsi_oversold", 35),
        ("adx_max", 25),
    )

    def __init__(self):
        super().__init__()
        self.bb = bt.indicators.BollingerBands(self.data.close, period=20, devfactor=2.0)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.macd = bt.indicators.MACD(self.data.close)
        self.adx = bt.indicators.AverageDirectionalMovementIndex(self.data, period=14)

    def has_long_signal(self) -> bool:
        if len(self.data) < 30:
            return False
        below_lower = self.data.close[0] < self.bb.lines.bot[0]
        rsi_oversold = self.rsi[0] < self.p.rsi_oversold
        macd_turning_up = (
            self.macd.lines.macd[0] > self.macd.lines.macd[-1]
            and self.macd.lines.macd[-1] <= self.macd.lines.macd[-2]
        )
        ranging = self.adx.adx[0] < self.p.adx_max
        return below_lower and rsi_oversold and macd_turning_up and ranging

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.has_long_signal():
                entry = self.data.close[0]
                stop = self.data.low[0] - 1.5 * self.atr[0]
                if stop >= entry:
                    return
                # Target = middle band (mean) OR rr_ratio * risk, whichever is closer.
                rr_target = entry + self.p.rr_ratio * (entry - stop)
                target = min(self.bb.lines.mid[0], rr_target)
                if target <= entry:
                    return
                size = self.calc_position_size(entry, stop)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.stop_price = stop
                    self.target_price = target
        else:
            rsi_overbought = self.rsi[0] > 60
            if (
                self.data.close[0] <= self.stop_price
                or self.data.close[0] >= self.target_price
                or rsi_overbought
            ):
                self.order = self.close()
```

---

## Bundle 3 — Breakout (`src/plutus/strategies/bundle_breakout.py`)

**Description.** Volatility-compression breakout. Waits for ATR to compress
versus its own moving average, then enters when price clears the prior N-day
high on a 2× volume surge.

**Indicators / patterns.** N-day high/low channel, ATR(14) vs ATR-SMA(20),
20-day volume SMA, RSI(14) ceiling.

**Best market regime.** Stocks emerging from a base — coiled volatility about
to release. Avoid in already-extended runs (RSI capped).

```python
# src/plutus/strategies/bundle_breakout.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class BreakoutBundle(BaseStrategy):
    """Bundle 3 — Consolidation breakout with volume confirmation."""

    params = (
        ("lookback", 20),
        ("vol_breakout_ratio", 2.0),
        ("atr_compress_ratio", 0.6),
        ("rsi_max", 75),
    )

    def __init__(self):
        super().__init__()
        self.highest = bt.indicators.Highest(self.data.high, period=self.p.lookback)
        self.lowest = bt.indicators.Lowest(self.data.low, period=self.p.lookback)
        self.atr_ma = bt.indicators.SMA(self.atr, period=20)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.vol_ma = bt.indicators.SMA(self.data.volume, period=20)

    def has_long_signal(self) -> bool:
        if len(self.data) < self.p.lookback + 2:
            return False
        breakout = self.data.close[0] > self.highest[-1]
        volume_surge = self.vol_ma[0] > 0 and self.data.volume[0] > self.p.vol_breakout_ratio * self.vol_ma[0]
        compressed = self.atr_ma[0] > 0 and self.atr[0] < self.p.atr_compress_ratio * self.atr_ma[0]
        rsi_ok = self.rsi[0] < self.p.rsi_max
        return breakout and volume_surge and compressed and rsi_ok

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.has_long_signal():
                entry = self.data.close[0]
                stop = max(self.lowest[0], entry - 2 * self.atr[0])
                if stop >= entry:
                    return
                # Measured-move target capped by rr_ratio.
                range_target = entry + (self.highest[0] - self.lowest[0])
                rr_target = entry + self.p.rr_ratio * (entry - stop)
                target = max(rr_target, range_target)
                size = self.calc_position_size(entry, stop)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.stop_price = stop
                    self.target_price = target
        else:
            # Trail stop to breakeven once price advances 1×ATR in our favor.
            if self.entry_price and self.data.close[0] > self.entry_price + self.atr[0]:
                self.stop_price = max(self.stop_price, self.entry_price)
            if self.data.close[0] <= self.stop_price or self.data.close[0] >= self.target_price:
                self.order = self.close()
```

---

## Bundle 4 — SMC (`src/plutus/strategies/bundle_smc.py`)

**Description.** Smart-Money Concepts. Long after a liquidity grab (sweep of a
recent swing low followed by reclaim) or when price taps an order-block zone
inside a constructive trend, with volume confirmation.

**Indicators / patterns.** Liquidity grabs, order blocks, fair-value gaps,
RSI(14), ATR(14), 20-day volume SMA.

**Best market regime.** Trending or volatile markets where institutional
footprints are visible. Weak in pure low-volatility chop.

```python
# src/plutus/strategies/bundle_smc.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class SMCBundle(BaseStrategy):
    """Bundle 4 — Smart Money Concepts: liquidity grab + order block + FVG."""

    params = (
        ("fvg_min_atr", 0.5),
        ("rsi_low", 30),
        ("rsi_high", 65),
        ("vol_min_ratio", 1.3),
    )

    def __init__(self):
        super().__init__()
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.vol_ma = bt.indicators.SMA(self.data.volume, period=20)

    # ---- pattern helpers ---------------------------------------------- #
    def _bullish_fvg(self) -> bool:
        if len(self.data) < 3:
            return False
        gap = self.data.low[0] - self.data.high[-2]
        return gap > 0 and gap > self.p.fvg_min_atr * self.atr[0]

    def _liquidity_grab(self) -> bool:
        if len(self.data) < 6:
            return False
        recent_low = min(self.data.low[-i] for i in range(1, 6))
        dipped = self.data.low[0] < recent_low
        reclaimed = self.data.close[0] > recent_low
        bullish_close = self.data.close[0] > self.data.open[0]
        return dipped and reclaimed and bullish_close

    def _near_order_block(self) -> bool:
        if len(self.data) < 11:
            return False
        for i in range(2, 10):
            bearish = self.data.close[-i] < self.data.open[-i]
            if not bearish:
                continue
            follow_through = all(
                self.data.close[-j] > self.data.open[-j] for j in range(0, i)
            )
            if follow_through:
                ob_high = self.data.high[-i]
                if abs(self.data.close[0] - ob_high) < self.atr[0]:
                    return True
        return False

    # ---- signal -------------------------------------------------------- #
    def has_long_signal(self) -> bool:
        if len(self.data) < 11:
            return False
        pattern = self._liquidity_grab() or self._bullish_fvg() or self._near_order_block()
        rsi_ok = self.p.rsi_low < self.rsi[0] < self.p.rsi_high
        vol_ok = self.vol_ma[0] > 0 and self.data.volume[0] > self.p.vol_min_ratio * self.vol_ma[0]
        return pattern and rsi_ok and vol_ok

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.has_long_signal():
                entry = self.data.close[0]
                stop = self.data.low[0] - self.atr[0]
                if stop >= entry:
                    return
                target = entry + self.p.rr_ratio * (entry - stop)
                size = self.calc_position_size(entry, stop)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.stop_price = stop
                    self.target_price = target
        else:
            if self.data.close[0] <= self.stop_price or self.data.close[0] >= self.target_price:
                self.order = self.close()
```

---

## Bundle 5 — Composite (`src/plutus/strategies/bundle_composite.py`)

**Description.** Composite is a peer Backtrader strategy. It imports the four
other bundle classes, instantiates each one's indicators on the same data feed
inside its own `__init__`, and on every bar polls each peer's
`has_long_signal()`. It enters long only when **at least 3 of the 4** peers
agree on the same bar.

**Why a peer, not a meta-filter.** Composite gets its own equity curve, its own
trade log, and its own row in `backtest_results`. The runner returns five
`BundleResult`s per symbol; Composite is one of them. See `07_backtesting.md`.

**Indicators / patterns.** Whatever the four peers expose. Composite creates no
indicators of its own beyond the inherited ATR (used for stop sizing).

**Best market regime.** Highest-conviction, lowest-frequency. Tends to fire
when both trend and breakout are confirming, or when reversal aligns with SMC.

```python
# src/plutus/strategies/bundle_composite.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy
from plutus.strategies.bundle_trend import TrendBundle
from plutus.strategies.bundle_reversal import ReversalBundle
from plutus.strategies.bundle_breakout import BreakoutBundle
from plutus.strategies.bundle_smc import SMCBundle


PEER_CLASSES = (TrendBundle, ReversalBundle, BreakoutBundle, SMCBundle)


class CompositeBundle(BaseStrategy):
    """Bundle 5 — peer strategy that requires 3-of-4 agreement among bundles 1–4."""

    params = (
        ("min_agreement", 3),   # number of peers that must agree on the same bar
    )

    def __init__(self):
        super().__init__()
        # Build a "shadow" instance of each peer that shares this strategy's
        # data feed. Each shadow's __init__ runs through the normal indicator-
        # construction path, so its bt.indicators.* objects are wired against
        # self.data. The shadow never receives next()/notify_*() callbacks
        # from Cerebro — Composite owns trade execution; the shadows only
        # serve has_long_signal().
        self.peers = [self._spawn_peer(cls) for cls in PEER_CLASSES]

    def _spawn_peer(self, peer_cls):
        peer = peer_cls.__new__(peer_cls)
        peer.data = self.data
        peer.datas = self.datas
        peer.broker = self.broker
        peer.p = peer_cls.params  # use peer's defaults; risk/rr come from this strategy
        peer.order = None
        peer.entry_price = None
        peer.stop_price = None
        peer.target_price = None
        peer.trade_log = []
        # Re-run the peer's __init__ body to register its indicators on self.data.
        # This relies on each peer's __init__ being a pure indicator-wiring
        # operation (no order placement) — which is the contract above.
        peer_cls.__init__(peer)
        return peer

    def has_long_signal(self) -> bool:
        agree = sum(1 for p in self.peers if p.has_long_signal())
        return agree >= self.p.min_agreement

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.has_long_signal():
                entry = self.data.close[0]
                stop = entry - 2 * self.atr[0]
                if stop >= entry:
                    return
                target = entry + self.p.rr_ratio * (entry - stop)
                size = self.calc_position_size(entry, stop)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.stop_price = stop
                    self.target_price = target
        else:
            if self.data.close[0] <= self.stop_price or self.data.close[0] >= self.target_price:
                self.order = self.close()
```

---

## `has_long_signal()` contract

| Class | Responsibility |
|---|---|
| `BaseStrategy.has_long_signal()` | Returns `False`. Pure stub so Composite can poll any subclass uniformly. |
| `TrendBundle.has_long_signal()` | True on bullish EMA cross + filter + RSI band + volume + ADX trend. |
| `ReversalBundle.has_long_signal()` | True on lower-BB tag + RSI oversold + MACD turning up in low ADX. |
| `BreakoutBundle.has_long_signal()` | True on N-day high break after ATR compression with volume surge. |
| `SMCBundle.has_long_signal()` | True on liquidity grab / FVG / order-block tap with RSI band + volume. |
| `CompositeBundle.has_long_signal()` | True iff `sum(p.has_long_signal() for p in self.peers) >= 3`. |

The method must be a **pure indicator read** — no calls to `self.position`,
`self.broker`, or `self.order`. This is what lets Composite reuse it on shadow
instances that never place orders.

---

## Strategy Bundle Signal Summary

| Bundle | Long entry trigger | Stop | Target | Best regime |
|---|---|---|---|---|
| Trend     | EMA9 crosses above EMA21 + price>EMA50 + RSI 50–72 + Vol>1.5×avg + ADX>20 | min(EMA21, close − 2×ATR) | close + `rr_ratio` × risk | Strong trends |
| Reversal  | Close < Lower BB + RSI<35 + MACD turning up + ADX<25 | low − 1.5×ATR | min(BB middle, close + `rr_ratio` × risk) | Sideways |
| Breakout  | Close > 20-day high + Vol>2×avg + ATR<0.6×ATR-SMA + RSI<75 | max(20-day low, close − 2×ATR) | max(measured move, close + `rr_ratio` × risk) | Post-base launches |
| SMC       | Liquidity grab OR FVG OR Order-block tap + Vol>1.3×avg + RSI 30–65 | low − 1×ATR | close + `rr_ratio` × risk | Trending / volatile |
| Composite | ≥3 of bundles 1–4 report `has_long_signal()` on the same bar | close − 2×ATR | close + `rr_ratio` × risk | Highest-conviction |

---

## File layout under `src/plutus/strategies/`

```
src/plutus/strategies/
├── __init__.py
├── base.py
├── bundle_trend.py
├── bundle_reversal.py
├── bundle_breakout.py
├── bundle_smc.py
└── bundle_composite.py
```

`__init__.py` exposes the five strategy classes for the runner:

```python
# src/plutus/strategies/__init__.py
from plutus.strategies.bundle_trend import TrendBundle
from plutus.strategies.bundle_reversal import ReversalBundle
from plutus.strategies.bundle_breakout import BreakoutBundle
from plutus.strategies.bundle_smc import SMCBundle
from plutus.strategies.bundle_composite import CompositeBundle

__all__ = [
    "TrendBundle",
    "ReversalBundle",
    "BreakoutBundle",
    "SMCBundle",
    "CompositeBundle",
]
```

The runner in `07_backtesting.md` consumes these classes via a single
`BUNDLE_MAP` dict with five keys: `trend`, `reversal`, `breakout`, `smc`,
`composite`.
