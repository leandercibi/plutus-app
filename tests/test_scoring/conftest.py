"""Shared fixtures for scoring tests."""
import pandas as pd
import numpy as np
import pytest


def _synthetic_ohlcv(
    n: int = 90,
    start_price: float = 1000.0,
    daily_pct: float = 0.003,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic OHLCV with a controllable trend."""
    np.random.seed(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    closes = [start_price]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + daily_pct + np.random.normal(0, 0.005)))

    df = pd.DataFrame({
        "Open":   [c * 0.995 for c in closes],
        "High":   [c * 1.010 for c in closes],
        "Low":    [c * 0.985 for c in closes],
        "Close":  closes,
        "Volume": [np.random.randint(500_000, 2_000_000) for _ in closes],
    }, index=idx)
    df.attrs["bars_fetched"]  = n
    df.attrs["bars_requested"] = n
    return df


@pytest.fixture
def uptrend_df():
    """Strong uptrend: EMA20 > EMA50, positive MACD."""
    from plutus.data.ohlcv import add_indicators
    df = _synthetic_ohlcv(n=90, daily_pct=0.006)
    return add_indicators(df)


@pytest.fixture
def downtrend_df():
    """Strong downtrend: EMA20 < EMA50, negative MACD."""
    from plutus.data.ohlcv import add_indicators
    df = _synthetic_ohlcv(n=90, daily_pct=-0.006)
    return add_indicators(df)


@pytest.fixture
def flat_df():
    """Flat price action."""
    from plutus.data.ohlcv import add_indicators
    df = _synthetic_ohlcv(n=90, daily_pct=0.0, seed=0)
    return add_indicators(df)


@pytest.fixture
def five_symbol_indicators():
    """Return 5 distinct indicator dfs with deliberately varying profiles."""
    from plutus.data.ohlcv import add_indicators

    profiles = {
        "RELIANCE":    (0.008, 42),   # strong uptrend
        "HDFCBANK":    (0.003, 43),   # mild uptrend
        "BHARTIARTL":  (0.000, 44),   # flat
        "INFY":        (-0.003, 45),  # mild downtrend
        "TATAMOTORS":  (-0.008, 46),  # strong downtrend
    }
    return {
        sym: add_indicators(_synthetic_ohlcv(n=90, daily_pct=pct, seed=seed))
        for sym, (pct, seed) in profiles.items()
    }
