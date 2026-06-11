from __future__ import annotations

import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window).mean()


def atr(candles: pd.DataFrame, period: int = 14) -> pd.Series:
    high = candles["high"]
    low = candles["low"]
    close = candles["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def delivery_adjusted_volume(delivery: pd.DataFrame) -> pd.Series:
    """A9. Volume weighted by delivery percentage."""
    return delivery["traded_qty"] * delivery["delivery_pct"]
