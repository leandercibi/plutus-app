# src/plutus/strategies/bundle_reversal.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class ReversalBundle(BaseStrategy):
    """Bundle 2 — Bollinger band mean reversion with RSI + MACD confirmation."""

    params = (
        ("rsi_oversold", 40),
        ("adx_max", 30),
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
        )
        # Need 2 of 3: below_lower, rsi_oversold, macd_turning_up
        signals = sum([below_lower, rsi_oversold, macd_turning_up])
        return signals >= 2

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
