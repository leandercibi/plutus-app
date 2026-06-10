# src/plutus/strategies/bundle_reversal.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class ReversalBundle(BaseStrategy):
    """
    Bundle 2 — Bollinger band mean reversion with RSI + MACD confirmation.

    Entry: 2-of-3 signals: below lower BB, RSI < 40, MACD turning up.
           Volume ≥ 1.3× 20-day avg.
    Regime gate: skips longs in strong BULL (trending market reduces reversal edge).
    Stops/targets: ATR-anchored (1.5× stop, 2× T1, 3× T2).
    """

    params = (
        ("rsi_oversold",  40),
        ("adx_max",       30),
        ("vol_min_ratio", 1.3),
    )

    def __init__(self):
        super().__init__()
        self.bb     = bt.indicators.BollingerBands(self.data.close, period=20, devfactor=2.0)
        self.rsi    = bt.indicators.RSI(self.data.close, period=14)
        self.macd   = bt.indicators.MACD(self.data.close)
        self.adx    = bt.indicators.AverageDirectionalMovementIndex(self.data, period=14)
        self.vol_ma = bt.indicators.SMA(self.data.volume, period=20)

    def has_long_signal(self) -> bool:
        if len(self.data) < 30:
            return False
        # Regime gate: skip in strongly trending (BULL or strongly directional) market
        if self.p.nifty_trend == "BULL" and self.adx.adx[0] > self.p.adx_max:
            return False
        vol_ok = self.vol_ma[0] > 0 and self.data.volume[0] >= self.p.vol_min_ratio * self.vol_ma[0]
        if not vol_ok:
            return False
        below_lower    = self.data.close[0] < self.bb.lines.bot[0]
        rsi_oversold   = self.rsi[0] < self.p.rsi_oversold
        macd_turning_up = self.macd.lines.macd[0] > self.macd.lines.macd[-1]
        return sum([below_lower, rsi_oversold, macd_turning_up]) >= 2

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
                    self.stop_price   = stop
                    self.t1_price     = t1
                    self.t2_price     = t2
                    self.target_price = t1
        else:
            rsi_overbought = self.rsi[0] > 60
            if (
                self.data.close[0] <= self.stop_price
                or (self.t2_price and self.data.close[0] >= self.t2_price)
                or (self.t1_price and self.data.close[0] >= self.t1_price)
                or rsi_overbought
            ):
                self.order = self.close()
