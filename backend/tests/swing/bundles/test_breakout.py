from __future__ import annotations

import numpy as np
import pandas as pd

from plutus.config.settings import Settings
from plutus.swing.bundles.base import BundleContext
from plutus.swing.bundles.breakout import BreakoutBundle


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


def _base(n: int = 60) -> tuple[list[float], pd.Series]:
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # range-bound around 100 for the first n-1 bars (Donchian-20 high ~101)
    close = [100.0 + np.sin(i / 3.0) for i in range(n - 1)]
    return close, dates


def _breakout_with_volume() -> tuple[pd.DataFrame, pd.DataFrame]:
    close, dates = _base()
    n = len(dates)
    donchian_high = max(close[-20:])
    close = close + [donchian_high + 1.5]  # clear the 20-day high modestly (< 2 ATR)
    close_arr = np.array(close)
    high = close_arr + 0.5
    high[-1] = close_arr[-1] + 0.5
    low = close_arr - 0.5
    open_ = close_arr - 0.2
    # delivery-adjusted volume spikes on the breakout bar
    traded = [1_000_000] * (n - 1) + [3_000_000]
    pct = [0.5] * (n - 1) + [0.6]
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


def _breakout_without_volume() -> tuple[pd.DataFrame, pd.DataFrame]:
    close, dates = _base()
    n = len(dates)
    donchian_high = max(close[-20:])
    close = close + [donchian_high + 3.0]
    close_arr = np.array(close)
    high = close_arr + 0.5
    low = close_arr - 0.5
    open_ = close_arr - 0.2
    # no volume expansion on the breakout bar
    traded = [1_000_000] * n
    pct = [0.5] * n
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


def _strong_breakout() -> tuple[pd.DataFrame, pd.DataFrame]:
    """A breakout that clears the Donchian high by more than 2 ATR (strong)."""
    close, dates = _base()
    n = len(dates)
    donchian_high = max(close[-20:])
    close = close + [donchian_high + 12.0]  # very large move
    close_arr = np.array(close)
    high = close_arr + 0.5
    low = close_arr - 0.5
    open_ = close_arr - 0.2
    traded = [1_000_000] * (n - 1) + [3_000_000]
    pct = [0.5] * (n - 1) + [0.6]
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


def _bundle() -> BreakoutBundle:
    return BreakoutBundle(Settings(_env_file=None))


def test_breakout_with_volume_produces_signal() -> None:
    candles, delivery = _breakout_with_volume()
    ctx = BundleContext(symbol="INFY", regime="BULL", delivery=delivery)
    signal = _bundle().fit_signal("INFY", candles, ctx)
    assert signal is not None
    assert signal.bundle == "breakout"
    assert signal.stop_loss < signal.entry
    assert signal.target_1 > signal.entry


def test_breakout_without_volume_returns_none() -> None:
    candles, delivery = _breakout_without_volume()
    ctx = BundleContext(symbol="INFY", regime="BULL", delivery=delivery)
    assert _bundle().fit_signal("INFY", candles, ctx) is None


def test_circuit_hit_suppresses_normal_breakout() -> None:
    candles, delivery = _breakout_with_volume()
    ctx = BundleContext(
        symbol="INFY",
        regime="BULL",
        delivery=delivery,
        extras={"circuit_recent_hit": True},
    )
    assert _bundle().fit_signal("INFY", candles, ctx) is None


def test_circuit_hit_allows_strong_breakout_above_2atr() -> None:
    candles, delivery = _strong_breakout()
    ctx = BundleContext(
        symbol="INFY",
        regime="BULL",
        delivery=delivery,
        extras={"circuit_recent_hit": True},
    )
    signal = _bundle().fit_signal("INFY", candles, ctx)
    assert signal is not None


def test_required_inputs() -> None:
    assert _bundle().required_inputs() == {"ohlcv", "delivery", "bulk_block"}
