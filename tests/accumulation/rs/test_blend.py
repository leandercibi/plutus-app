from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from plutus.accumulation.rs.blend import RSBlend


def _candles(returns_path: list[float], n: int = 200) -> pd.DataFrame:
    """Build a close series of length n; the last `len(returns_path)` closes follow
    the provided multiplicative path for deterministic returns."""
    closes = np.full(n, 100.0)
    return pd.DataFrame({"close": closes})


def _series_from_total_returns(r30: float, r90: float, r180: float, n: int = 200) -> pd.DataFrame:
    # construct close so that close[-1]/close[-31] etc give the wanted returns
    close = np.full(n, 100.0, dtype=float)
    close[-1] = 100.0
    close[-31] = close[-1] / (1.0 + r30)
    close[-91] = close[-1] / (1.0 + r90)
    close[-181] = close[-1] / (1.0 + r180)
    return pd.DataFrame({"close": close})


@pytest.fixture
def rs() -> RSBlend:
    return RSBlend()


def test_blended_weight_schedule() -> None:
    rs = RSBlend()
    stock = _series_from_total_returns(0.30, 0.20, 0.10)
    nifty = _series_from_total_returns(0.10, 0.10, 0.05)
    result = rs.compute(stock, nifty)
    # rs_30 = 0.30 - 0.10 = 0.20; rs_90 = 0.20-0.10=0.10; rs_180=0.10-0.05=0.05
    assert result.rs_30 == pytest.approx(0.20, abs=1e-6)
    assert result.rs_90 == pytest.approx(0.10, abs=1e-6)
    assert result.rs_180 == pytest.approx(0.05, abs=1e-6)
    expected_blend = 0.2 * 0.20 + 0.4 * 0.10 + 0.4 * 0.05
    assert result.blended == pytest.approx(expected_blend, abs=1e-6)


def test_short_horizon_noise_does_not_dominate(rs: RSBlend) -> None:
    # huge positive 30d spike but flat 90/180 -> blended stays modest (weight 0.2)
    stock = _series_from_total_returns(1.00, 0.0, 0.0)
    nifty = _series_from_total_returns(0.0, 0.0, 0.0)
    result = rs.compute(stock, nifty)
    assert result.rs_30 == pytest.approx(1.00, abs=1e-6)
    # blended only gets 0.2 weight on the spike
    assert result.blended == pytest.approx(0.2 * 1.00, abs=1e-6)
    assert result.blended < result.rs_30
