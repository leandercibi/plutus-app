from __future__ import annotations

from datetime import date

import pytest

from plutus.shared.benchmarks.random_liquid import RandomLiquidBaseline
from plutus.shared.types import BacktestTrade


def _trades() -> list[BacktestTrade]:
    return [
        BacktestTrade(
            symbol="INFY",
            bundle="trend",
            regime="BULL",
            entry_date=date(2024, 1, 1),
            exit_date=date(2024, 1, 6),
            realized_R=1.2,
            hold_days=5,
        ),
        BacktestTrade(
            symbol="TCS",
            bundle="breakout",
            regime="BULL",
            entry_date=date(2024, 1, 10),
            exit_date=date(2024, 1, 13),
            realized_R=-0.8,
            hold_days=3,
        ),
    ]


_UNIVERSE: dict[date, frozenset[str]] = {
    date(2024, 1, 1): frozenset({"AAA", "BBB", "CCC"}),
    date(2024, 1, 10): frozenset({"DDD", "EEE"}),
}


def _universe_at(d: date) -> frozenset[str]:
    return _UNIVERSE[d]


def _returns_for(symbol: str, entry: date, hold: int) -> float:
    # deterministic fake return keyed by symbol
    table = {"AAA": 0.05, "BBB": -0.02, "CCC": 0.10, "DDD": 0.01, "EEE": -0.03}
    return table[symbol]


def test_matched_trade_count() -> None:
    base = RandomLiquidBaseline(seed=42)
    curve = base.matched_trade_curve(_trades(), _universe_at, _returns_for)
    # one equity point per trade plus the starting 1.0
    assert len(curve) == len(_trades()) + 1


def test_deterministic_with_same_seed() -> None:
    a = RandomLiquidBaseline(seed=42).matched_trade_curve(_trades(), _universe_at, _returns_for)
    b = RandomLiquidBaseline(seed=42).matched_trade_curve(_trades(), _universe_at, _returns_for)
    assert list(a.round(8)) == pytest.approx(list(b.round(8)))


def test_starts_at_one() -> None:
    curve = RandomLiquidBaseline(seed=42).matched_trade_curve(_trades(), _universe_at, _returns_for)
    assert curve.iloc[0] == pytest.approx(1.0)
