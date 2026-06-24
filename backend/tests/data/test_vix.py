from __future__ import annotations

from datetime import date

import pandas as pd

from plutus.data.vix import fetch_india_vix, latest_india_vix


class _StubVix:
    def __init__(self, series: pd.Series) -> None:
        self._series = series

    def fetch(self, start: date, end: date) -> pd.Series:
        return self._series


def _provider() -> _StubVix:
    idx = pd.date_range("2025-01-01", periods=4, freq="D")
    return _StubVix(pd.Series([12.0, 13.5, 15.0, 14.2], index=idx))


def test_series_indexed_in_time_order() -> None:
    s = fetch_india_vix(date(2025, 1, 1), date(2025, 1, 4), _provider())
    assert list(s.index) == sorted(s.index)


def test_latest_value_present_for_last_day() -> None:
    val = latest_india_vix(date(2025, 1, 1), date(2025, 1, 4), _provider())
    assert val == 14.2
