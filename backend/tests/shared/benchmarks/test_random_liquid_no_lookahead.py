from __future__ import annotations

from datetime import date

from plutus.shared.benchmarks.random_liquid import RandomLiquidBaseline
from plutus.shared.types import BacktestTrade

_UNIVERSE: dict[date, frozenset[str]] = {
    date(2024, 2, 1): frozenset({"AAA", "BBB"}),
    date(2024, 2, 5): frozenset({"CCC", "DDD", "EEE"}),
}


def _universe_at(d: date) -> frozenset[str]:
    return _UNIVERSE[d]


def _returns_for(symbol: str, entry: date, hold: int) -> float:
    return 0.01


def _trades() -> list[BacktestTrade]:
    return [
        BacktestTrade(
            symbol="X",
            bundle="trend",
            regime="BULL",
            entry_date=date(2024, 2, 1),
            exit_date=date(2024, 2, 4),
            realized_R=1.0,
            hold_days=3,
        ),
        BacktestTrade(
            symbol="Y",
            bundle="trend",
            regime="BULL",
            entry_date=date(2024, 2, 5),
            exit_date=date(2024, 2, 9),
            realized_R=1.0,
            hold_days=4,
        ),
    ]


def test_picks_only_from_pit_universe_of_entry_day() -> None:
    base = RandomLiquidBaseline(seed=7)
    picks = base.matched_picks(_trades(), _universe_at)
    assert len(picks) == 2
    for trade, picked_symbol, hold_days in picks:
        assert picked_symbol in _universe_at(trade.entry_date)
        assert hold_days == trade.hold_days
