# src/plutus/strategies/bundle_breakout.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class BreakoutBundle(BaseStrategy):
    """Bundle 3 — Consolidation breakout with volume confirmation."""

    params = (
        ("lookback", 20),
        ("vol_breakout_ratio", 1.3),
        ("atr_compress_ratio", 0.9),
        ("rsi_max", 80),
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
        rsi_ok = self.rsi[0] < self.p.rsi_max
        return breakout and volume_surge and rsi_ok

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
