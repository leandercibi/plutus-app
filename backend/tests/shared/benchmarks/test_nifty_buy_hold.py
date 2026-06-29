from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from plutus.shared.benchmarks.nifty_buy_hold import NiftyBuyHold


def _series() -> pd.Series:
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    return pd.Series([100.0, 110.0, 121.0, 121.0], index=idx)


def test_curve_starts_at_one() -> None:
    curve = NiftyBuyHold().equity_curve(date(2024, 1, 1), date(2024, 1, 4), _series())
    assert curve.iloc[0] == pytest.approx(1.0)


def test_curve_matches_reference() -> None:
    curve = NiftyBuyHold().equity_curve(date(2024, 1, 1), date(2024, 1, 4), _series())
    # normalized: 100->1.0, 110->1.1, 121->1.21, 121->1.21
    assert list(curve.round(6)) == pytest.approx([1.0, 1.1, 1.21, 1.21])


def test_curve_clips_to_window() -> None:
    idx = pd.to_datetime(
        [
            "2023-12-31",
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
        ]
    )
    s = pd.Series([90.0, 100.0, 110.0, 121.0, 121.0, 130.0], index=idx)
    curve = NiftyBuyHold().equity_curve(date(2024, 1, 1), date(2024, 1, 4), s)
    assert curve.index.min() == pd.Timestamp("2024-01-01")
    assert curve.index.max() == pd.Timestamp("2024-01-04")
    assert curve.iloc[0] == pytest.approx(1.0)
