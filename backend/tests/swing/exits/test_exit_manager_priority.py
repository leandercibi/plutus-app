from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from plutus.config.settings import Settings
from plutus.shared.cost_model.slippage import SlippageModel
from plutus.shared.fills.policy import FillPolicy
from plutus.shared.fills.types import OHLCBar, TradePlan
from plutus.swing.exits.exit_manager import ExitManager, OpenTradeView


@pytest.fixture
def manager() -> ExitManager:
    settings = Settings(_env_file=None)
    return ExitManager(settings, FillPolicy(SlippageModel(settings)))


def _plan() -> TradePlan:
    return TradePlan(
        symbol="INFY",
        signal_date=date(2025, 1, 1),
        entry=Decimal("100"),
        stop_loss=Decimal("95"),
        target_1=Decimal("110"),
        target_2=Decimal("120"),
    )


def _flat_candles(n: int) -> pd.DataFrame:
    # flat price -> no_progress would trigger, but stop must win on the breach bar
    closes = [100.0] * n
    return pd.DataFrame(
        {
            "high": [Decimal("100")] * n,
            "low": [Decimal("100")] * n,
            "close": [Decimal(str(c)) for c in closes],
        }
    )


def test_stop_wins_over_no_progress_on_same_bar(manager: ExitManager) -> None:
    # build a flat, no-progress window, but today's bar breaches the stop
    candles = _flat_candles(6)
    today_bar = OHLCBar(
        as_of=date(2025, 1, 10),
        open=Decimal("96"),
        high=Decimal("97"),
        low=Decimal("94"),  # breaches stop 95
        close=Decimal("95"),
    )
    view = OpenTradeView(
        plan=_plan(),
        entry_idx=0,
        current_idx=5,  # elapsed 0.5 of horizon 10 -> no_progress would fire
        horizon_max_days=10,
        adv=1_000_000,
        atr_pct=0.02,
    )
    decision = manager.tick(view, candles, today_bar)
    assert decision.action == "STOP"
    assert decision.fill is not None
    assert decision.reason


def test_no_exit_when_nothing_triggers(manager: ExitManager) -> None:
    # strong progress, no stop breach
    candles = pd.DataFrame(
        {
            "high": [Decimal(str(h)) for h in [101, 103, 105, 107, 108, 109]],
            "low": [Decimal(str(lo)) for lo in [100, 102, 104, 106, 107, 108]],
            "close": [
                Decimal(str(c)) for c in [100.5, 102.5, 104.5, 106.5, 107.5, 108.5]
            ],
        }
    )
    today_bar = OHLCBar(
        as_of=date(2025, 1, 10),
        open=Decimal("108"),
        high=Decimal("109"),
        low=Decimal("107"),  # above stop 95
        close=Decimal("108.5"),
    )
    view = OpenTradeView(
        plan=_plan(),
        entry_idx=0,
        current_idx=5,
        horizon_max_days=10,
        adv=1_000_000,
        atr_pct=0.02,
    )
    decision = manager.tick(view, candles, today_bar)
    assert decision.action == "HOLD"
    assert decision.fill is None
