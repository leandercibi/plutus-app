from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from plutus.shared.benchmarks.strip import BenchmarkResult, BenchmarkStrip
from plutus.shared.types import BacktestTrade


def _trades() -> list[BacktestTrade]:
    return [
        BacktestTrade("A", "trend", "BULL", date(2024, 1, 1), date(2024, 1, 5), 2.0, 4),
        BacktestTrade("B", "trend", "BULL", date(2024, 1, 6), date(2024, 1, 9), -1.0, 3),
        BacktestTrade("C", "trend", "BULL", date(2024, 1, 10), date(2024, 1, 12), 1.0, 2),
    ]


def _curve(start: float, end: float) -> pd.Series:
    return pd.Series([start, end], index=pd.to_datetime(["2024-01-01", "2024-01-12"]))


def test_all_four_numbers_present() -> None:
    res = BenchmarkStrip().compute(
        plutus_trades=_trades(),
        plutus_curve=_curve(1.0, 1.30),
        nifty_curve=_curve(1.0, 1.10),
        regime_curve=_curve(1.0, 1.05),
        random_curve=_curve(1.0, 1.02),
    )
    assert isinstance(res, BenchmarkResult)
    assert res.plutus_net_pct == pytest.approx(30.0)
    assert res.nifty_net_pct == pytest.approx(10.0)
    assert res.regime_switched_net_pct == pytest.approx(5.0)
    assert res.random_liquid_net_pct == pytest.approx(2.0)
    assert res.plutus_n_trades == 3


def test_profit_factor_from_realized_r() -> None:
    res = BenchmarkStrip().compute(
        plutus_trades=_trades(),
        plutus_curve=_curve(1.0, 1.30),
        nifty_curve=_curve(1.0, 1.10),
        regime_curve=_curve(1.0, 1.05),
        random_curve=_curve(1.0, 1.02),
    )
    # gains = 2.0 + 1.0 = 3.0 ; losses = 1.0 ; pf = 3.0
    assert res.plutus_profit_factor == pytest.approx(3.0)


def test_profit_factor_infinite_when_no_losses() -> None:
    trades = [
        BacktestTrade("A", "trend", "BULL", date(2024, 1, 1), date(2024, 1, 5), 2.0, 4),
        BacktestTrade("B", "trend", "BULL", date(2024, 1, 6), date(2024, 1, 9), 1.0, 3),
    ]
    res = BenchmarkStrip().compute(
        plutus_trades=trades,
        plutus_curve=_curve(1.0, 1.30),
        nifty_curve=_curve(1.0, 1.10),
        regime_curve=_curve(1.0, 1.05),
        random_curve=_curve(1.0, 1.02),
    )
    assert res.plutus_profit_factor == float("inf")
