from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from plutus.config.settings import Settings
from plutus.shared.cost_model.slippage import SlippageModel
from plutus.shared.fills.policy import FillPolicy
from plutus.shared.fills.types import OHLCBar, TradePlan
from plutus.swing.exits.stop import StopExit


@pytest.fixture
def fills() -> FillPolicy:
    return FillPolicy(SlippageModel(Settings(_env_file=None)))


def _plan() -> TradePlan:
    return TradePlan(
        symbol="INFY",
        signal_date=date(2025, 1, 1),
        entry=Decimal("100"),
        stop_loss=Decimal("95"),
        target_1=Decimal("110"),
        target_2=Decimal("120"),
    )


def _bar(o: str, h: str, lo: str, c: str) -> OHLCBar:
    return OHLCBar(
        as_of=date(2025, 1, 3),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(lo),
        close=Decimal(c),
    )


def test_sl_hit_returns_fill_via_fill_policy(fills: FillPolicy) -> None:
    exit = StopExit()
    # low dips to stop level
    bar = _bar("97", "98", "94", "96")
    result = exit.check(_plan(), bar, fills, adv=1_000_000, atr_pct=0.02)
    assert result is not None
    assert result.side == "SELL"
    assert result.price < Decimal("95")  # stop minus sell slippage


def test_sl_not_hit_returns_none(fills: FillPolicy) -> None:
    exit = StopExit()
    bar = _bar("101", "105", "98", "104")  # low 98 > stop 95
    result = exit.check(_plan(), bar, fills, adv=1_000_000, atr_pct=0.02)
    assert result is None
