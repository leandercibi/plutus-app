from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from plutus.shared.benchmarks.regime_switched import RegimeSwitched


def _closes() -> pd.Series:
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    return pd.Series([100.0, 110.0, 121.0, 121.0, 133.1], index=idx)


def test_bear_periods_are_flat() -> None:
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    regimes = pd.Series(["BULL", "BEAR", "BEAR", "BEAR", "BEAR"], index=idx)
    curve = RegimeSwitched().equity_curve(date(2024, 1, 1), date(2024, 1, 5), _closes(), regimes)
    # day1 BULL captures day1's return relative to day0; from day2 on BEAR -> flat
    # return on a day is applied when prior day's label is BULL (long into that day).
    assert curve.iloc[-1] == curve.iloc[1]  # flat after the first BULL day


def test_compounds_only_during_bull() -> None:
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    # BULL throughout -> tracks nifty returns exactly
    regimes = pd.Series(["BULL"] * 5, index=idx)
    curve = RegimeSwitched().equity_curve(date(2024, 1, 1), date(2024, 1, 5), _closes(), regimes)
    nifty = _closes() / _closes().iloc[0]
    assert list(curve.round(6)) == pytest.approx(list(nifty.round(6)))


def test_starts_at_one() -> None:
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    regimes = pd.Series(["BEAR"] * 5, index=idx)
    curve = RegimeSwitched().equity_curve(date(2024, 1, 1), date(2024, 1, 5), _closes(), regimes)
    assert curve.iloc[0] == pytest.approx(1.0)
    # all BEAR -> totally flat at 1.0
    assert list(curve.round(6)) == pytest.approx([1.0, 1.0, 1.0, 1.0, 1.0])
