from __future__ import annotations

from decimal import Decimal

import pandas as pd

from plutus.config.settings import Settings
from plutus.swing.exits.no_progress import NoProgressExit, NoProgressInput


def _candles(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": [Decimal(str(c)) for c in closes]})


def _settings() -> Settings:
    # thresholds: t1 progress < 0.3 by elapsed >= 0.5 of window
    return Settings(_env_file=None)


def test_below_threshold_at_midpoint_exits() -> None:
    # entry 100, stop 95 (risk 5), T1 110 => +2R move to target.
    # at midpoint of a 10-day window, price barely moved -> realized R toward T1 tiny.
    candles = _candles([100, 100.2, 100.1, 100.3, 100.2, 100.4])
    exit = NoProgressExit(_settings())
    inp = NoProgressInput(
        entry=Decimal("100"),
        stop_loss=Decimal("95"),
        target_1=Decimal("110"),
        entry_idx=0,
        current_idx=5,  # day 5 of 10 -> elapsed 0.5
        horizon_max_days=10,
    )
    assert exit.should_exit(inp, candles) is True


def test_above_threshold_holds() -> None:
    # by midpoint, price already moved most of the way to T1 -> progress strong, hold.
    candles = _candles([100, 102, 104, 106, 107, 108])
    exit = NoProgressExit(_settings())
    inp = NoProgressInput(
        entry=Decimal("100"),
        stop_loss=Decimal("95"),
        target_1=Decimal("110"),
        entry_idx=0,
        current_idx=5,
        horizon_max_days=10,
    )
    assert exit.should_exit(inp, candles) is False


def test_early_in_window_holds_even_if_flat() -> None:
    # elapsed < 0.5 -> never exits for no-progress yet
    candles = _candles([100, 100.1, 100.2])
    exit = NoProgressExit(_settings())
    inp = NoProgressInput(
        entry=Decimal("100"),
        stop_loss=Decimal("95"),
        target_1=Decimal("110"),
        entry_idx=0,
        current_idx=2,  # day 2 of 10 -> elapsed 0.2
        horizon_max_days=10,
    )
    assert exit.should_exit(inp, candles) is False
