from __future__ import annotations

from decimal import Decimal

import pandas as pd

from plutus.swing.exits.trailing import EMATrail


def _candles(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": [Decimal(str(c)) for c in closes]})


def test_stop_tracks_ema() -> None:
    closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    candles = _candles(closes)
    trail = EMATrail()
    stop = trail.trail_stop(candles, ema_period=5)
    # EMA of a rising series sits below the last close, above the first
    assert Decimal("100") < stop < Decimal("109")


def test_ema_rises_with_rising_closes() -> None:
    flat = _candles([100] * 10)
    rising = _candles([100, 102, 104, 106, 108, 110, 112, 114, 116, 118])
    trail = EMATrail()
    flat_stop = trail.trail_stop(flat, ema_period=5)
    rising_stop = trail.trail_stop(rising, ema_period=5)
    assert rising_stop > flat_stop
