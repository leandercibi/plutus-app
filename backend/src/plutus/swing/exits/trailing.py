from __future__ import annotations

from decimal import Decimal

import pandas as pd


def _atr(candles: pd.DataFrame, end_idx: int, period: int) -> Decimal:
    """ATR over the window ending at end_idx (inclusive), using high-low range.

    A close-less true range is sufficient here; bundles backtest the parameters.
    """
    start = max(0, end_idx - period + 1)
    highs = candles["high"].iloc[start : end_idx + 1]
    lows = candles["low"].iloc[start : end_idx + 1]
    ranges = [Decimal(str(h)) - Decimal(str(lo)) for h, lo in zip(highs, lows, strict=True)]
    if not ranges:
        return Decimal("0")
    return sum(ranges, Decimal("0")) / Decimal(len(ranges))


class ChandelierTrail:
    def trail_stop(
        self,
        candles: pd.DataFrame,
        entry_idx: int,
        current_idx: int,
        n_atr: float,
        atr_period: int,
    ) -> Decimal:
        highs = candles["high"].iloc[entry_idx : current_idx + 1]
        highest_high = max(Decimal(str(h)) for h in highs)
        atr = _atr(candles, current_idx, atr_period)
        return highest_high - Decimal(str(n_atr)) * atr


class EMATrail:
    def trail_stop(self, candles: pd.DataFrame, ema_period: int) -> Decimal:
        closes = [Decimal(str(c)) for c in candles["close"]]
        alpha = Decimal("2") / (Decimal(ema_period) + Decimal("1"))
        ema = closes[0]
        for price in closes[1:]:
            ema = alpha * price + (Decimal("1") - alpha) * ema
        return ema
