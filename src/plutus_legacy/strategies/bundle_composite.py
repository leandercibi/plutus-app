# src/plutus/strategies/bundle_composite.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class CompositeBundle(BaseStrategy):
    """
    Bundle 5 — requires agreement among bundles 1–4.

    Entry: ≥ 2 of the 4 peer signals agree on the current bar,
           plus Volume ≥ 1.3× avg.
    Stops/targets: ATR-anchored (1.5× stop, 2× T1, 3× T2); explicit R:R check.
    """

    params = (
        ("min_agreement", 2),
        ("vol_min_ratio", 1.3),
    )

    def __init__(self):
        super().__init__()
        self.ema9 = bt.indicators.EMA(self.data.close, period=9)
        self.ema21 = bt.indicators.EMA(self.data.close, period=21)
        self.ema50 = bt.indicators.EMA(self.data.close, period=50)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.adx = bt.indicators.AverageDirectionalMovementIndex(self.data, period=14)
        self.boll = bt.indicators.BollingerBands(
            self.data.close, period=20, devfactor=2.0
        )
        self.vol_ma = bt.indicators.SMA(self.data.volume, period=20)

    def _trend_signal(self) -> bool:
        if self.p.nifty_trend == "BEAR":
            return False
        ema_aligned = self.ema9[0] > self.ema21[0] > self.ema50[0]
        adx_strong = self.adx.adx[0] > 20
        rsi_ok = 40 < self.rsi[0] < 70
        return ema_aligned and adx_strong and rsi_ok

    def _reversal_signal(self) -> bool:
        rsi_oversold = self.rsi[0] < 35
        near_lower_bb = self.data.close[0] <= self.boll.bot[0] * 1.01
        bullish_bar = self.data.close[0] > self.data.open[0]
        return rsi_oversold and near_lower_bb and bullish_bar

    def _breakout_signal(self) -> bool:
        if len(self.data) < 21:
            return False
        if self.p.nifty_trend == "BEAR":
            return False
        high_20 = max(self.data.high[-i] for i in range(1, 21))
        price_break = self.data.close[0] > high_20
        vol_surge = self.vol_ma[0] > 0 and (self.data.volume[0] / self.vol_ma[0]) >= 1.5
        return price_break and vol_surge

    def _smc_signal(self) -> bool:
        if len(self.data) < 6:
            return False
        recent_low = min(self.data.low[-i] for i in range(1, 6))
        dipped_below = self.data.low[0] < recent_low
        closed_above = self.data.close[0] > recent_low
        bullish_bar = self.data.close[0] > self.data.open[0]
        rsi_ok = 30 < self.rsi[0] < 65
        return dipped_below and closed_above and bullish_bar and rsi_ok

    def has_long_signal(self) -> bool:
        if len(self.data) < 55:
            return False
        # Volume gate applies at the composite level
        vol_ok = (
            self.vol_ma[0] > 0
            and self.data.volume[0] >= self.p.vol_min_ratio * self.vol_ma[0]
        )
        if not vol_ok:
            return False
        signals = [
            self._trend_signal(),
            self._reversal_signal(),
            self._breakout_signal(),
            self._smc_signal(),
        ]
        return sum(signals) >= self.p.min_agreement

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
            if (
                self.data.close[0] <= self.stop_price
                or (self.t2_price and self.data.close[0] >= self.t2_price)
                or (self.t1_price and self.data.close[0] >= self.t1_price)
            ):
                self.order = self.close()
