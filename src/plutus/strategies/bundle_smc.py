# strategies/bundle_smc.py
import backtrader as bt

from plutus.strategies.base import BaseStrategy


class SMCBundle(BaseStrategy):
    """
    Bundle 4: Smart Money Concepts — FVG, Order Blocks, Liquidity Grabs.
    Works in trending and volatile markets.
    """
    params = (
        ("fvg_min_size_atr", 0.5),   # FVG must be at least 0.5×ATR
        ("liq_grab_bars", 3),         # look for reversal within 3 bars of sweep
        ("min_rr", 2.0),             # minimum reward-to-risk ratio
    )

    def __init__(self):
        super().__init__()
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.volume_sma = bt.indicators.SMA(self.data.volume, period=20)

    def _detect_bullish_fvg(self) -> bool:
        """
        Bullish FVG: candle[0].low > candle[-2].high
        (current candle's low is above 2 bars ago's high = gap left unfilled)
        Wait for price to return to gap.
        """
        if len(self.data) < 3:
            return False
        gap_size = self.data.low[0] - self.data.high[-2]
        return gap_size > 0 and gap_size > self.p.fvg_min_size_atr * self.atr[0]

    def _detect_liquidity_grab(self) -> bool:
        """
        Liquidity grab: price dips below recent low then closes back above it.
        Indicates stop hunt → reversal likely.
        """
        if len(self.data) < 5:
            return False
        recent_low = min(self.data.low[-i] for i in range(1, 6))
        dipped_below = self.data.low[0] < recent_low
        closed_above = self.data.close[0] > recent_low
        strong_close = self.data.close[0] > self.data.open[0]  # bullish candle
        return dipped_below and closed_above and strong_close

    def _detect_order_block(self) -> float:
        """
        Order block: last bearish candle before a sequence of 3+ bullish candles.
        Returns the high of that bearish candle as the OB zone top.
        """
        for i in range(1, 10):
            if self.data.close[-i] < self.data.open[-i]:  # bearish candle
                # Check if followed by bullish momentum
                bullish_follow = all(
                    self.data.close[-j] > self.data.open[-j]
                    for j in range(0, i)
                )
                if bullish_follow:
                    return self.data.high[-i]
        return 0.0

    def next(self):
        if self.order:
            return

        if not self.position:
            liq_grab = self._detect_liquidity_grab()
            ob_zone = self._detect_order_block()
            near_ob = ob_zone > 0 and abs(self.data.close[0] - ob_zone) < self.atr[0]
            rsi_ok = 30 < self.rsi[0] < 65
            volume_ok = (self.data.volume[0] / self.volume_sma[0]) > 1.3 if self.volume_sma[0] > 0 else False

            if (liq_grab or near_ob) and rsi_ok and volume_ok:
                stop = self.data.low[0] - self.atr[0]
                target = self.data.close[0] + 3 * self.atr[0]
                rr = (target - self.data.close[0]) / (self.data.close[0] - stop)

                if rr >= self.p.min_rr:
                    size = self.calc_position_size(self.data.close[0], stop)
                    if size > 0:
                        self.order = self.buy(size=size)
                        self.stop_price = stop
                        self.target_price = target

        else:
            if self.data.close[0] < self.stop_price or self.data.close[0] >= self.target_price:
                self.order = self.close()
