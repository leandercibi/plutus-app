# src/plutus/strategies/bundle_trend.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class TrendBundle(BaseStrategy):
    """
    Bundle 1 — EMA crossover trend follower.

    Entry: EMA9 crosses above EMA21, close > EMA50, RSI 45–75,
           ADX > 18, Volume ≥ 1.3× 20-day avg.
    Regime gate: skips longs when nifty_trend == "BEAR".
    Stops/targets: ATR-anchored (1.5× stop, 2× T1, 3× T2).
    """

    params = (
        ("ema_fast", 9),
        ("ema_slow", 21),
        ("ema_filter", 50),
        ("rsi_min", 45),
        ("rsi_max", 75),
        ("adx_min", 18),
        ("vol_min_ratio", 1.3),  # upgraded from 1.0 → 1.3
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
        if self.p.nifty_trend == "BEAR":
            return False
        cross_up = (
            self.ema_fast[0] > self.ema_slow[0]
            and self.ema_fast[-1] <= self.ema_slow[-1]
        )
        above_filter = self.data.close[0] > self.ema_filter[0]
        rsi_ok = self.p.rsi_min < self.rsi[0] < self.p.rsi_max
        vol_ok = (
            self.vol_ma[0] > 0
            and self.data.volume[0] >= self.p.vol_min_ratio * self.vol_ma[0]
        )
        adx_ok = self.adx.adx[0] > self.p.adx_min
        return cross_up and above_filter and rsi_ok and vol_ok and adx_ok

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
                    self.t1_price = t1
                    self.t2_price = t2
                    self.target_price = t1
        else:
            ema_cross_down = self.ema_fast[0] < self.ema_slow[0]
            if (
                self.data.close[0] <= self.stop_price
                or (self.t2_price and self.data.close[0] >= self.t2_price)
                or (self.t1_price and self.data.close[0] >= self.t1_price)
                or ema_cross_down
            ):
                self.order = self.close()
