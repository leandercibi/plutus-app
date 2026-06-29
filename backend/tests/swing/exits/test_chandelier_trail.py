from __future__ import annotations

from decimal import Decimal

import pandas as pd

from plutus.swing.exits.trailing import ChandelierTrail


def _candles(
    highs: list[float], lows: list[float], closes: list[float]
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "high": [Decimal(str(h)) for h in highs],
            "low": [Decimal(str(lo)) for lo in lows],
            "close": [Decimal(str(c)) for c in closes],
        }
    )


def test_trail_uses_highest_high_minus_n_atr() -> None:
    # constant 1-wide range => ATR ~ 1.0; highest high 110 over window
    highs = [101, 103, 105, 108, 110]
    lows = [100, 102, 104, 107, 109]
    closes = [100.5, 102.5, 104.5, 107.5, 109.5]
    candles = _candles(highs, lows, closes)
    trail = ChandelierTrail()
    stop = trail.trail_stop(
        candles, entry_idx=0, current_idx=4, n_atr=3.0, atr_period=3
    )
    # stop must be below the highest high
    assert stop < Decimal("110")


def test_trail_tightens_as_new_highs_print() -> None:
    highs = [101, 103, 105, 108, 112, 116]
    lows = [100, 102, 104, 107, 111, 115]
    closes = [100.5, 102.5, 104.5, 107.5, 111.5, 115.5]
    candles = _candles(highs, lows, closes)
    trail = ChandelierTrail()
    earlier = trail.trail_stop(
        candles, entry_idx=0, current_idx=3, n_atr=3.0, atr_period=3
    )
    later = trail.trail_stop(
        candles, entry_idx=0, current_idx=5, n_atr=3.0, atr_period=3
    )
    # as price makes new highs, the trailing stop ratchets up
    assert later > earlier
