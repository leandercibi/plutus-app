# src/plutus/strategies/bundle_breakout.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class BreakoutBundle(BaseStrategy):
    """
    Bundle 3 — Consolidation breakout with volume confirmation.

    Entry: close breaks above 20-day high, Volume ≥ 1.3× avg, RSI < 80.
    Regime gate: skips longs in BEAR. Sector gate: skips if sector_rs_rank > 3
                 (only fires when sector is in top-3 by relative strength).
    Stops/targets: ATR-anchored (1.5× stop, 2× T1, 3× T2).
    Trail stop to break-even once price advances 1× ATR in our favour.
    """

    params = (
        ("lookback", 20),
        ("vol_breakout_ratio", 1.3),
        ("rsi_max", 80),
        ("sector_rs_top_n", 3),  # only fire if sector rank ≤ this value
    )

    def __init__(self):
        super().__init__()
        self.highest = bt.indicators.Highest(self.data.high, period=self.p.lookback)
        self.lowest = bt.indicators.Lowest(self.data.low, period=self.p.lookback)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.vol_ma = bt.indicators.SMA(self.data.volume, period=20)

    def has_long_signal(self) -> bool:
        if len(self.data) < self.p.lookback + 2:
            return False
        # Regime gate: no breakout longs in a confirmed BEAR
        if self.p.nifty_trend == "BEAR":
            return False
        # Sector gate: only fire in top-N sectors by RS rank
        if (
            self.p.sector_rs_rank is not None
            and self.p.sector_rs_rank > self.p.sector_rs_top_n
        ):
            return False
        breakout = self.data.close[0] > self.highest[-1]
        vol_surge = (
            self.vol_ma[0] > 0
            and self.data.volume[0] >= self.p.vol_breakout_ratio * self.vol_ma[0]
        )
        rsi_ok = self.rsi[0] < self.p.rsi_max
        return breakout and vol_surge and rsi_ok

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
            # Trail stop to break-even once 1× ATR in our favour
            if self.entry_price and self.data.close[0] > self.entry_price + self.atr[0]:
                self.stop_price = max(self.stop_price, self.entry_price)
            if (
                self.data.close[0] <= self.stop_price
                or (self.t2_price and self.data.close[0] >= self.t2_price)
                or (self.t1_price and self.data.close[0] >= self.t1_price)
            ):
                self.order = self.close()
