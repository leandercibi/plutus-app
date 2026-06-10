# src/plutus/strategies/bundle_smc.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class SMCBundle(BaseStrategy):
    """
    Bundle 4 — Smart Money Concepts (liquidity grab + order block confluence).

    Entry: liquidity grab (dip-below-recent-low + bullish close) OR price near
           an order block, confirmed by RSI 30–65 and Volume ≥ 1.3× avg.
    Stops/targets: ATR-anchored (1.5× stop, 2× T1, 3× T2); explicit R:R ≥ 2.0 check.
    """

    params = (
        ("vol_min_ratio", 1.3),
        ("rsi_min",       30),
        ("rsi_max",       65),
    )

    def __init__(self):
        super().__init__()
        self.rsi      = bt.indicators.RSI(self.data.close, period=14)
        self.vol_ma   = bt.indicators.SMA(self.data.volume, period=20)

    def _detect_liquidity_grab(self) -> bool:
        if len(self.data) < 6:
            return False
        recent_low   = min(self.data.low[-i] for i in range(1, 6))
        dipped_below = self.data.low[0] < recent_low
        closed_above = self.data.close[0] > recent_low
        bullish_bar  = self.data.close[0] > self.data.open[0]
        return dipped_below and closed_above and bullish_bar

    def _detect_order_block(self) -> float:
        """Return high of the last bearish candle before 3+ bullish follow-through, or 0."""
        for i in range(1, 10):
            if self.data.close[-i] < self.data.open[-i]:
                bullish_follow = all(
                    self.data.close[-j] > self.data.open[-j]
                    for j in range(0, i)
                )
                if bullish_follow:
                    return self.data.high[-i]
        return 0.0

    def has_long_signal(self) -> bool:
        if len(self.data) < 15:
            return False
        vol_ok  = self.vol_ma[0] > 0 and self.data.volume[0] >= self.p.vol_min_ratio * self.vol_ma[0]
        rsi_ok  = self.p.rsi_min < self.rsi[0] < self.p.rsi_max
        if not (vol_ok and rsi_ok):
            return False
        liq_grab = self._detect_liquidity_grab()
        ob_zone  = self._detect_order_block()
        near_ob  = ob_zone > 0 and abs(self.data.close[0] - ob_zone) < self.atr[0]
        return liq_grab or near_ob

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
            if (
                self.data.close[0] <= self.stop_price
                or (self.t2_price and self.data.close[0] >= self.t2_price)
                or (self.t1_price and self.data.close[0] >= self.t1_price)
            ):
                self.order = self.close()
