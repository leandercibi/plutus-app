# src/plutus/strategies/bundle_trend.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class TrendBundle(BaseStrategy):
    """Bundle 1 — EMA crossover trend follower."""

    params = (
        ("ema_fast", 9),
        ("ema_slow", 21),
        ("ema_filter", 50),
        ("rsi_min", 45),
        ("rsi_max", 75),
        ("adx_min", 18),
        ("vol_min_ratio", 1.0),
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
