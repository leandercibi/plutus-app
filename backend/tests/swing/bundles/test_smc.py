from __future__ import annotations

import numpy as np
import pandas as pd

from plutus.config.settings import Settings
from plutus.swing.bundles.base import BundleContext
from plutus.swing.bundles.smc import SMCBundle


def _candles(n: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # an order-block style move: drop then a strong reclaim
    close = list(np.linspace(120.0, 100.0, 40)) + list(np.linspace(100.0, 115.0, 20))
    close_arr = np.array(close)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close_arr - 0.3,
            "high": close_arr + 0.6,
            "low": close_arr - 0.6,
            "close": close_arr,
            "volume": [1_000_000] * n,
        }
    )


def _bundle() -> SMCBundle:
    return SMCBundle(Settings(_env_file=None))


def test_smc_produces_signal_with_bundle_smc() -> None:
    ctx = BundleContext(symbol="INFY", regime="BULL")
    signal = _bundle().fit_signal("INFY", _candles(), ctx)
    assert signal is not None
    assert signal.bundle == "smc"
    assert "display_only" in signal.reasons
    assert signal.stop_loss < signal.entry
    assert signal.target_1 > signal.entry


def test_required_inputs() -> None:
    assert _bundle().required_inputs() == {"ohlcv"}
