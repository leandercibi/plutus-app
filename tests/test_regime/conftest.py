"""Fixtures for regime tests."""
import pandas as pd
import numpy as np
import pytest


def _make_index_df(close_values: list[float], start: str = "2025-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(close_values), freq="B")
    opens = [c * 0.99 for c in close_values]
    df = pd.DataFrame({
        "Open": opens,
        "High": [c * 1.01 for c in close_values],
        "Low": [c * 0.98 for c in close_values],
        "Close": close_values,
        "Volume": [1_000_000] * len(close_values),
    }, index=idx)
    df.attrs["bars_fetched"] = len(df)
    df.attrs["bars_requested"] = len(df)
    return df


def _trending_close(start: float, daily_pct: float, n: int = 120) -> list[float]:
    values = [start]
    for _ in range(n - 1):
        values.append(values[-1] * (1 + daily_pct))
    return values


@pytest.fixture
def synthetic_bull_nifty_df():
    """Strongly uptrending: Close well above EMA50, positive slope."""
    return _make_index_df(_trending_close(20000, 0.004, 120))


@pytest.fixture
def synthetic_bear_nifty_df():
    """Strongly downtrending: Close well below EMA50, negative slope."""
    return _make_index_df(_trending_close(22000, -0.004, 120))


@pytest.fixture
def synthetic_flat_nifty_df():
    """Flat/oscillating around a mean."""
    np.random.seed(42)
    values = [22000 + np.random.uniform(-100, 100) for _ in range(120)]
    return _make_index_df(values)


@pytest.fixture
def sector_dfs():
    """IT outperforms (+15%), METAL underperforms (-5%) vs Nifty flat (+2%)."""
    nifty = _make_index_df(_trending_close(22000, 0.0003, 65))   # ~2% over 60 bars
    it    = _make_index_df(_trending_close(35000, 0.0022, 65))   # ~15% over 60 bars
    metal = _make_index_df(_trending_close(8000,  -0.0008, 65))  # ~-5% over 60 bars
    return {"NIFTY_50": nifty, "NIFTY_IT": it, "NIFTY_METAL": metal}
