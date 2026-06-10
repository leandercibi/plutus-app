# src/plutus/strategies/bundle_vcp.py
"""
VCPBundle — Minervini-style Volatility Contraction Pattern.

Signal conditions:
  1. At least 3 consecutive contraction stages: each pullback's ATR is smaller
     than the previous one (measured over 5-bar windows).
  2. Price is above EMA50 (uptrend filter).
  3. RSI(14) on the bar BEFORE the breakout in 50–70 zone (momentum check on the
     pre-breakout bar; the breakout bar itself always inflates RSI, so using rsi[-1]
     tests whether the stock was in a healthy zone going into the pivot, not during it).
  4. Pivot breakout: current close > highest close in last 20 bars.
  5. Volume surge on breakout bar: volume ≥ vol_breakout_ratio × 20-bar avg.
  6. Regime gate: skip when nifty_trend == "BEAR".

Stops/targets: ATR-anchored (1.5× stop, 2× T1, 3× T2).
R:R check uses T2 (3×ATR / 1.5×ATR = 2.0 exactly meets the 2.0 floor).
"""
import backtrader as bt
from plutus.strategies.base import BaseStrategy


class VCPBundle(BaseStrategy):
    """Bundle 6 — Volatility Contraction Pattern."""

    params = (
        ("vol_breakout_ratio", 1.5),   # volume on pivot bar must be ≥ 1.5× avg
        ("rsi_min",            50),    # RSI floor for momentum confirmation
        ("rsi_max",            70),    # RSI ceiling — avoid overbought entries
        ("n_contractions",     3),     # minimum number of contraction stages
        ("contraction_window", 5),     # bars per ATR measurement window
        ("pivot_lookback",     20),    # bars for pivot-high detection
        ("sector_rs_top_n",    5),     # sector must be in top-N (relaxed vs breakout)
    )

    def __init__(self):
        super().__init__()
        self.ema50   = bt.indicators.EMA(self.data.close, period=50)
        self.rsi     = bt.indicators.RSI(self.data.close, period=14)
        self.vol_ma  = bt.indicators.SMA(self.data.volume, period=20)

    def _atr_of_window(self, start: int) -> float:
        """Approximate ATR as mean true-range over a 5-bar window ending at -start."""
        trs = []
        for i in range(start, start + self.p.contraction_window):
            h = self.data.high[-i]
            l = self.data.low[-i]
            c_prev = self.data.close[-(i + 1)]
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            trs.append(tr)
        return sum(trs) / len(trs) if trs else 0.0

    def _has_vcp_contractions(self) -> bool:
        """Check that the last n_contractions ATR windows show decreasing range."""
        w = self.p.contraction_window
        n = self.p.n_contractions
        min_bars = (n + 1) * w + 1
        if len(self.data) < min_bars:
            return False
        atrs = [self._atr_of_window(i * w) for i in range(n + 1)]
        # Each successive (older) window must be larger: atrs[0] < atrs[1] < atrs[2]...
        return all(atrs[i] < atrs[i + 1] for i in range(n))

    def has_long_signal(self) -> bool:
        min_warmup = 50 + self.p.pivot_lookback + (self.p.n_contractions + 1) * self.p.contraction_window
        if len(self.data) < min_warmup:
            return False

        # Regime gate
        if self.p.nifty_trend == "BEAR":
            return False

        # Sector gate: only fire if sector is in top-N by RS rank
        if self.p.sector_rs_rank is not None and self.p.sector_rs_rank > self.p.sector_rs_top_n:
            return False

        # Uptrend filter
        if self.data.close[0] <= self.ema50[0]:
            return False

        # RSI momentum zone — check the bar BEFORE the breakout.
        # The breakout bar itself always inflates RSI; checking rsi[-1] tests whether
        # momentum was healthy going into the pivot, not on the high-volume spike bar.
        if not (self.p.rsi_min <= self.rsi[-1] <= self.p.rsi_max):
            return False

        # Pivot breakout: current close > highest of previous pivot_lookback bars
        if len(self.data) < self.p.pivot_lookback + 1:
            return False
        pivot_high = max(self.data.close[-i] for i in range(1, self.p.pivot_lookback + 1))
        if self.data.close[0] <= pivot_high:
            return False

        # Volume surge on breakout bar
        if self.vol_ma[0] <= 0:
            return False
        if self.data.volume[0] < self.p.vol_breakout_ratio * self.vol_ma[0]:
            return False

        # VCP contraction pattern
        return self._has_vcp_contractions()

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.has_long_signal():
                entry = self.data.close[0]
                stop, t1, t2 = self.atr_stops_and_targets(entry)
                if stop >= entry or not self.rr_ok(entry, stop, t2):
                    return
                size = self.calc_position_size(entry, stop)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.stop_price = stop
                    self.t1_price   = t1
                    self.t2_price   = t2
        else:
            if (
                self.data.close[0] <= self.stop_price
                or (self.t2_price and self.data.close[0] >= self.t2_price)
                or (self.t1_price and self.data.close[0] >= self.t1_price)
            ):
                self.order = self.close()
