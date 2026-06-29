from __future__ import annotations

import numpy as np
import pandas as pd

from plutus.config.settings import Settings
from plutus.swing.bundles.base import BundleContext
from plutus.swing.bundles.vcp import VCPBundle


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


def _contraction(
    center: float, amplitude: float, length: int, volume: int
) -> dict[str, list]:
    """A single contraction: oscillation of given amplitude around center."""
    closes = [center + amplitude * np.sin(i) for i in range(length)]
    return {
        "close": closes,
        "high": [c + amplitude * 0.3 for c in closes],
        "low": [c - amplitude * 0.3 for c in closes],
        "open": [c - 0.1 for c in closes],
        "volume": [volume] * length,
    }


def _vcp_candles() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Three contractions of decreasing amplitude on declining volume, then a
    breakout from the final contraction on expanding delivery-adjusted volume."""
    parts: dict[str, list] = {
        "close": [],
        "high": [],
        "low": [],
        "open": [],
        "volume": [],
    }

    # contraction 1: wide amplitude, high volume
    for part in (
        _contraction(100.0, 6.0, 12, 2_000_000),
        _contraction(100.0, 4.0, 10, 1_400_000),
        _contraction(100.0, 2.0, 8, 900_000),
    ):
        for k in parts:
            parts[k].extend(part[k])

    # breakout bar from the final (tightest) contraction
    parts["close"].append(108.0)
    parts["high"].append(108.5)
    parts["low"].append(106.0)
    parts["open"].append(101.0)
    parts["volume"].append(3_000_000)

    n = len(parts["close"])
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    candles = pd.DataFrame(
        {
            "date": dates,
            "open": parts["open"],
            "high": parts["high"],
            "low": parts["low"],
            "close": parts["close"],
            "volume": parts["volume"],
        }
    )
    pct = [0.5] * (n - 1) + [0.65]
    delivery = _delivery_frame(dates, parts["volume"], pct)
    return candles, delivery, n


def _bundle() -> VCPBundle:
    return VCPBundle(Settings(_env_file=None))


def test_three_contractions_then_breakout_produces_signal() -> None:
    candles, delivery, _ = _vcp_candles()
    ctx = BundleContext(symbol="INFY", regime="BULL", delivery=delivery)
    signal = _bundle().fit_signal("INFY", candles, ctx)
    assert signal is not None
    assert signal.bundle == "vcp"
    assert signal.stop_loss < signal.entry
    assert signal.target_1 > signal.entry


def test_circuit_affected_bars_excluded_from_contraction_count() -> None:
    """Marking enough bars as circuit-affected drops the usable contraction count
    below the minimum, so no signal is produced."""
    candles, delivery, n = _vcp_candles()
    # mark the entire first contraction window as circuit-affected
    circuit_bars = set(range(0, 12))
    ctx = BundleContext(
        symbol="INFY",
        regime="BULL",
        delivery=delivery,
        extras={"circuit_bars": circuit_bars},
    )
    assert _bundle().fit_signal("INFY", candles, ctx) is None


def test_required_inputs() -> None:
    assert _bundle().required_inputs() == {"ohlcv", "delivery"}
