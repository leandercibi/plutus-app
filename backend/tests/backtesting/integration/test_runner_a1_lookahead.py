from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from plutus.backtesting.runner import BacktestConfig, BacktestRunner
from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal

_RUNNER_SRC = Path(__file__).parents[3] / "src" / "plutus" / "backtesting" / "runner.py"


def _candles() -> pd.DataFrame:
    days = pd.date_range("2025-01-01", periods=10, freq="D")
    base = [100, 101, 103, 106, 110, 112, 111, 113, 115, 118]
    return pd.DataFrame(
        {
            "date": days,
            "open": base,
            "high": [b + 2 for b in base],
            "low": [b - 2 for b in base],
            "close": base,
        }
    )


def _fit_on_first_day(
    symbol: str, candles: pd.DataFrame, day: date
) -> BundleSignal | None:
    if day != date(2025, 1, 1):
        return None
    return BundleSignal(
        symbol=symbol,
        bundle="trend",
        as_of=day,
        entry=Decimal("100"),
        stop_loss=Decimal("96"),
        target_1=Decimal("112"),
        target_2=Decimal("120"),
    )


def _run(use_costs: bool) -> object:
    runner = BacktestRunner(Settings(_env_file=None))
    cfg = BacktestConfig(
        start=date(2025, 1, 1),
        end=date(2025, 1, 5),
        bundles=["trend"],
        use_cost_model=use_costs,
    )
    candles = _candles()
    return runner.run(
        cfg,
        get_universe_at=lambda d: frozenset({"INFY"}),
        candles_for=lambda s: candles,
        regime_at=lambda d: "BULL",
        fit_signal=_fit_on_first_day,
        adv_for=lambda s: 1_000_000,
        atr_pct_for=lambda s: 0.02,
    )


@pytest.mark.hallmark
def test_runner_no_same_bar_lookahead() -> None:
    """A1: a signal on bar T never produces a fill on bar T."""
    result = _run(use_costs=True)
    assert result.fills_before_signal == 0
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_date > date(2025, 1, 1)


def test_runner_costs_reduce_realized_r() -> None:
    with_costs = _run(use_costs=True).trades[0].realized_R
    no_costs = _run(use_costs=False).trades[0].realized_R
    assert with_costs < no_costs


def test_runner_uses_pit_universe_not_live() -> None:
    """A1/A17 CI guard: the runner must not call a live-universe accessor."""
    src = _RUNNER_SRC.read_text()
    tree = ast.parse(src)
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            called.add(node.attr)
        if isinstance(node, ast.Name):
            called.add(node.id)
    assert "get_live_universe" not in called
    assert "get_universe_at" in src
