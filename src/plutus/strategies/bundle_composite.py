# src/plutus/strategies/bundle_composite.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class CompositeBundle(BaseStrategy):
    """Bundle 5 — peer strategy that requires 3-of-4 agreement among bundles 1–4.
    
    Instead of spawning peer strategy instances (which breaks backtrader's lifecycle),
    we replicate the signal logic from each peer using shared indicators.
    """

    params = (
        ("min_agreement", 2),   # number of peers that must agree on the same bar
    )

    def __init__(self):
        super().__init__()
        # Shared indicators used across peer signal checks
        self.ema9 = bt.indicators.EMA(self.data.close, period=9)
        self.ema21 = bt.indicators.EMA(self.data.close, period=21)
        self.ema50 = bt.indicators.EMA(self.data.close, period=50)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.adx = bt.indicators.AverageDirectionalMovementIndex(self.data, period=14)
        self.boll = bt.indicators.BollingerBands(self.data.close, period=20, devfactor=2.0)
        self.volume_sma = bt.indicators.SMA(self.data.volume, period=20)

    def _trend_signal(self) -> bool:
        """Trend bundle logic: EMA9 > EMA21 > EMA50, ADX > 20, RSI 40-70."""
        ema_aligned = self.ema9[0] > self.ema21[0] > self.ema50[0]
        adx_strong = self.adx.adx[0] > 20
        rsi_ok = 40 < self.rsi[0] < 70
        return ema_aligned and adx_strong and rsi_ok

    def _reversal_signal(self) -> bool:
        """Reversal bundle logic: RSI oversold bounce + price near lower Bollinger."""
        rsi_oversold = self.rsi[0] < 35
        near_lower_band = self.data.close[0] <= self.boll.bot[0] * 1.01
        bullish_candle = self.data.close[0] > self.data.open[0]
        return rsi_oversold and near_lower_band and bullish_candle

    def _breakout_signal(self) -> bool:
        """Breakout bundle logic: price breaks above 20-day high with volume surge."""
        if len(self.data) < 21:
            return False
        high_20 = max(self.data.high[-i] for i in range(1, 21))
        price_break = self.data.close[0] > high_20
        vol_surge = (self.data.volume[0] / self.volume_sma[0]) > 1.5 if self.volume_sma[0] > 0 else False
        return price_break and vol_surge

    def _smc_signal(self) -> bool:
        """SMC bundle logic: liquidity grab + RSI filter."""
        if len(self.data) < 6:
            return False
        recent_low = min(self.data.low[-i] for i in range(1, 6))
        dipped_below = self.data.low[0] < recent_low
        closed_above = self.data.close[0] > recent_low
        strong_close = self.data.close[0] > self.data.open[0]
        rsi_ok = 30 < self.rsi[0] < 65
        return dipped_below and closed_above and strong_close and rsi_ok

    def has_long_signal(self) -> bool:
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
