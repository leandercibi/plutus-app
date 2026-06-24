from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd

from plutus.config.settings import Settings
from plutus.swing.bundles.base import BundleContext
from plutus.swing.bundles.trend import TrendBundle


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


def _trend_pullback_candles() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean uptrend (50DMA > 200DMA) then a shallow pullback to the 50DMA
    on contracting delivery-adjusted volume."""
    n = 210
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # steady rise from 50 -> 150 over the first 200 bars
    close = list(np.linspace(50.0, 150.0, n - 10))
    # pullback: last 10 bars drift down toward the rising 50DMA, then settle near it
    last = close[-1]
    pullback = [last - i * 1.0 for i in range(1, 11)]
    close = close + pullback
    close_arr = np.array(close)

    high = close_arr + 0.6
    low = close_arr - 0.6
    open_ = close_arr - 0.2

    # volume: normal during trend, contracting during the 10-bar pullback
    volume = [1_000_000] * (n - 10) + [400_000 - i * 10_000 for i in range(10)]
    # delivery pct: high during trend, lower during pullback (volume contraction)
    pct = [0.6] * (n - 10) + [0.4] * 10

    candles = pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close_arr,
            "volume": volume,
        }
    )
    delivery = _delivery_frame(dates, volume, pct)
    return candles, delivery


def _no_pullback_candles() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Uptrend with price far above the 50DMA (no pullback near it)."""
    n = 210
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = np.linspace(50.0, 200.0, n)
    # final bars accelerate up — price is well above 50DMA
    close[-5:] = close[-5:] + np.arange(1, 6) * 5
    high = close + 0.6
    low = close - 0.6
    open_ = close - 0.2
    volume = [1_000_000] * n
    pct = [0.6] * n
    candles = pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
    return candles, _delivery_frame(dates, volume, pct)


def _downtrend_candles() -> tuple[pd.DataFrame, pd.DataFrame]:
    """50DMA < 200DMA — no trend setup."""
    n = 210
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = np.linspace(200.0, 60.0, n)
    high = close + 0.6
    low = close - 0.6
    open_ = close - 0.2
    volume = [1_000_000] * n
    pct = [0.6] * n
    candles = pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
    return candles, _delivery_frame(dates, volume, pct)


def _bundle() -> TrendBundle:
    return TrendBundle(Settings(_env_file=None))


def test_clean_pullback_produces_signal_with_stop_below_pullback_low() -> None:
    candles, delivery = _trend_pullback_candles()
    ctx = BundleContext(symbol="INFY", regime="BULL", delivery=delivery)
    signal = _bundle().fit_signal("INFY", candles, ctx)

    assert signal is not None
    assert signal.bundle == "trend"
    pullback_low = Decimal(str(candles["low"].iloc[-10:].min()))
    assert signal.stop_loss < pullback_low
    # geometry sanity: stop below entry, targets above entry
    assert signal.stop_loss < signal.entry
    assert signal.target_1 > signal.entry
    assert signal.target_2 > signal.entry


def test_no_pullback_returns_none() -> None:
    candles, delivery = _no_pullback_candles()
    ctx = BundleContext(symbol="INFY", regime="BULL", delivery=delivery)
    assert _bundle().fit_signal("INFY", candles, ctx) is None


def test_downtrend_returns_none() -> None:
    candles, delivery = _downtrend_candles()
    ctx = BundleContext(symbol="INFY", regime="BEAR", delivery=delivery)
    assert _bundle().fit_signal("INFY", candles, ctx) is None


def test_required_inputs() -> None:
    assert _bundle().required_inputs() == {"ohlcv", "delivery"}
