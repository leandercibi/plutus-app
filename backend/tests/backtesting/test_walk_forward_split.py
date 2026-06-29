from __future__ import annotations

import pandas as pd
import pytest

from plutus.backtesting.walk_forward import split_walk_forward


def make_bars(n: int) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.DataFrame({"date": dates, "close": range(n)})


def test_window_split_count() -> None:
    """90 bars, window=30, step=7 ⇒ ≈ 8–9 windows."""
    bars = make_bars(90)
    windows = list(split_walk_forward(bars, window_days=30, step_days=7))
    assert 7 <= len(windows) <= 9


def test_each_window_has_is_and_oos() -> None:
    """IS = 70% of 30 = 21 bars; OOS = 30% = 9 bars."""
    bars = make_bars(90)
    w = next(split_walk_forward(bars, window_days=30, step_days=7))
    assert len(w["is_bars"]) == pytest.approx(21, abs=2)
    assert len(w["oos_bars"]) == pytest.approx(9, abs=2)


def test_no_lookahead_leak() -> None:
    """IS rows must have lower index than OOS rows in every window."""
    bars = make_bars(90)
    for w in split_walk_forward(bars, window_days=30, step_days=7):
        assert w["is_bars"].index.max() < w["oos_bars"].index.min()


def test_stops_before_window_exceeds_bars() -> None:
    """Never yields a window that extends past the end of bars."""
    bars = make_bars(40)
    for w in split_walk_forward(bars, window_days=30, step_days=7):
        assert len(w["is_bars"]) + len(w["oos_bars"]) <= 30


def test_empty_bars_yields_nothing() -> None:
    bars = make_bars(0)
    assert list(split_walk_forward(bars, window_days=30, step_days=7)) == []


def test_bars_smaller_than_window_yields_nothing() -> None:
    bars = make_bars(20)
    assert list(split_walk_forward(bars, window_days=30, step_days=7)) == []
