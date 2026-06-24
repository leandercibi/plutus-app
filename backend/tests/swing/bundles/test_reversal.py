from __future__ import annotations

import numpy as np
import pandas as pd

from plutus.config.settings import Settings
from plutus.swing.bundles.base import BundleContext
from plutus.swing.bundles.reversal import ReversalBundle


def _delivery_frame(
    dates: pd.Series, traded: list[int], pct: list[float]
) -> pd.DataFrame:
    delivery_qty = [int(t * p) for t, p in zip(traded, pct, strict=True)]
    return pd.DataFrame(
        {
            "date": dates,
            "traded_qty": traded,
            "delivery_qty": delivery_qty,
            "delivery_pct": pct,
        }
    )


def _engulfing_after_downtrend(with_volume: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = 40
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # flat then 5 declining closes below the 20DMA, then a bullish engulfing bar
    close = [100.0] * (n - 7)
    # drift down for the 6 bars before the engulfing
    close += [99.0, 97.5, 96.0, 94.5, 93.0, 92.0]
    # engulfing bar: opens below prior close, closes above prior open -> strong up
    close += [97.0]
    close_arr = np.array(close, dtype=float)

    open_ = close_arr - 0.3
    # the bar before the engulfing must be bearish (close below open)
    open_[-2] = close_arr[-2] + 1.0
    # last bar is the engulfing candle
    open_[-1] = close_arr[-2] - 0.5  # opens below prior close
    high = close_arr + 0.5
    low = close_arr - 0.5
    low[-1] = open_[-1] - 0.3
    high[-1] = close_arr[-1] + 0.3

    traded = [1_000_000] * n
    pct = [0.5] * n
    if with_volume:
        traded[-1] = 2_500_000  # delivery-adjusted volume confirmation
        pct[-1] = 0.6
    candles = pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close_arr,
            "volume": traded,
        }
    )
    return candles, _delivery_frame(dates, traded, pct)


def _bundle() -> ReversalBundle:
    return ReversalBundle(Settings(_env_file=None))


def test_engulfing_after_five_down_closes_with_volume_produces_signal() -> None:
    candles, delivery = _engulfing_after_downtrend(with_volume=True)
    ctx = BundleContext(symbol="INFY", regime="SIDEWAYS", delivery=delivery)
    signal = _bundle().fit_signal("INFY", candles, ctx)
    assert signal is not None
    assert signal.bundle == "reversal"
    assert signal.stop_loss < signal.entry
    assert signal.target_1 > signal.entry


def test_engulfing_without_delivery_confirmation_returns_none() -> None:
    candles, delivery = _engulfing_after_downtrend(with_volume=False)
    ctx = BundleContext(symbol="INFY", regime="SIDEWAYS", delivery=delivery)
    assert _bundle().fit_signal("INFY", candles, ctx) is None


def test_required_inputs() -> None:
    assert _bundle().required_inputs() == {"ohlcv", "delivery"}
