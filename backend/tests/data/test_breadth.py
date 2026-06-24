from __future__ import annotations

from datetime import date

import pandas as pd

from plutus.data.breadth import (
    fetch_advance_decline,
    fetch_pct_above_dma,
    latest_pct_above_dma,
)


class _StubBreadth:
    def __init__(self, pct_series: dict[int, pd.Series], ad: pd.Series) -> None:
        self._pct = pct_series
        self._ad = ad

    def fetch_pct_above_dma(self, window: int, start: date, end: date) -> pd.Series:
        return self._pct[window]

    def fetch_advance_decline(self, start: date, end: date) -> pd.Series:
        return self._ad


def _provider() -> _StubBreadth:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    pct50 = pd.Series([0.6, 0.55, 0.7], index=idx)
    pct200 = pd.Series([0.4, 0.45, 0.5], index=idx)
    ad = pd.Series([1.5, 0.8, 2.0], index=idx)  # >1 advancers dominate
    return _StubBreadth({50: pct50, 200: pct200}, ad)


def test_pct_above_dma_in_unit_range() -> None:
    series = fetch_pct_above_dma(50, date(2025, 1, 1), date(2025, 1, 3), _provider())
    assert series.min() >= 0.0
    assert series.max() <= 1.0


def test_advance_decline_sign_matches_fixture() -> None:
    ad = fetch_advance_decline(date(2025, 1, 1), date(2025, 1, 3), _provider())
    # day 1 advancers dominate (>1), day 2 decliners dominate (<1)
    assert ad.iloc[0] > 1.0
    assert ad.iloc[1] < 1.0


def test_latest_pct_above_dma_returns_last_value() -> None:
    val = latest_pct_above_dma(50, date(2025, 1, 1), date(2025, 1, 3), _provider())
    assert val == 0.7
