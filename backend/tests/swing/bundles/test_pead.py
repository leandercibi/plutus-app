from __future__ import annotations

import numpy as np
import pandas as pd

from plutus.config.settings import Settings
from plutus.swing.bundles.base import BundleContext
from plutus.swing.bundles.pead import PEADBundle


def _candles(n: int = 30) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = np.linspace(100.0, 112.0, n)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.3,
            "high": close + 0.6,
            "low": close - 0.6,
            "close": close,
            "volume": [1_000_000] * n,
        }
    )


def _bundle() -> PEADBundle:
    return PEADBundle(Settings(_env_file=None))


def test_no_earnings_in_last_5_sessions_returns_none() -> None:
    ctx = BundleContext(
        symbol="INFY",
        regime="BULL",
        extras={"earnings_in_last_5_sessions": False, "verified_earnings": True},
    )
    assert _bundle().fit_signal("INFY", _candles(), ctx) is None


def test_unverified_earnings_returns_none() -> None:
    ctx = BundleContext(
        symbol="INFY",
        regime="BULL",
        extras={"earnings_in_last_5_sessions": True, "verified_earnings": False},
    )
    assert _bundle().fit_signal("INFY", _candles(), ctx) is None


def test_earnings_and_verified_produces_paper_only_signal() -> None:
    ctx = BundleContext(
        symbol="INFY",
        regime="BULL",
        extras={"earnings_in_last_5_sessions": True, "verified_earnings": True},
    )
    signal = _bundle().fit_signal("INFY", _candles(), ctx)
    assert signal is not None
    assert signal.bundle == "pead"
    assert "paper_only" in signal.reasons


def test_required_inputs() -> None:
    assert _bundle().required_inputs() == {"ohlcv", "earnings"}
