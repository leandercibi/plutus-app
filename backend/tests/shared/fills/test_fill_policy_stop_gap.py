from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from plutus.config.settings import Settings
from plutus.shared.cost_model.slippage import SlippageModel
from plutus.shared.fills.policy import FillPolicy, FillResult
from plutus.shared.fills.types import OHLCBar, TradePlan


@pytest.fixture
def policy() -> FillPolicy:
    return FillPolicy(SlippageModel(Settings(_env_file=None)))


def _bar(d: date, o: str, h: str, low: str, c: str) -> OHLCBar:
    return OHLCBar(
        as_of=d,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
    )


def _plan() -> TradePlan:
    return TradePlan(
        symbol="INFY",
        signal_date=date(2025, 1, 1),
        entry=Decimal("100"),
        stop_loss=Decimal("95"),
        target_1=Decimal("110"),
        target_2=Decimal("120"),
    )


def test_entry_fills_at_next_bar_open_plus_slippage(policy: FillPolicy) -> None:
    plan = _plan()
    next_bar = _bar(date(2025, 1, 2), "101", "105", "100", "104")
    fill = policy.fill_entry(plan, next_bar, adv=1_000_000, atr_pct=0.02)
    assert isinstance(fill, FillResult)
    # BUY pays more than the open
    assert fill.price > Decimal("101")
    assert fill.filled_at.date() == date(2025, 1, 2)


def test_entry_never_fills_on_signal_bar(policy: FillPolicy) -> None:
    plan = _plan()
    next_bar = _bar(date(2025, 1, 2), "101", "105", "100", "104")
    fill = policy.fill_entry(plan, next_bar, adv=1_000_000, atr_pct=0.02)
    assert fill.filled_at.date() > plan.signal_date


def test_stop_normal_low_touches_open_above(policy: FillPolicy) -> None:
    plan = _plan()
    # opens at 97 (above stop 95), low dips to 94 (touches stop)
    next_bar = _bar(date(2025, 1, 3), "97", "98", "94", "96")
    fill = policy.fill_stop(plan, next_bar, adv=1_000_000, atr_pct=0.02)
    assert fill is not None
    # fill at worse of (stop=95, open=97) = 95, minus sell slippage
    assert fill.price < Decimal("95")
    assert fill.price > Decimal("94")


def test_stop_gap_through_fills_at_open_worse_than_stop(policy: FillPolicy) -> None:
    """A1 HALLMARK: gap-down opens below stop -> fill at open (worse), not at stop."""
    plan = _plan()
    next_bar = _bar(date(2025, 1, 3), "90", "92", "89", "91")  # opens 90 < stop 95
    fill = policy.fill_stop(plan, next_bar, adv=1_000_000, atr_pct=0.02)
    assert fill is not None
    # worse of (stop=95, open=90) = 90, then sell slippage makes it even lower
    assert fill.price < Decimal("90")


def test_stop_not_triggered_returns_none(policy: FillPolicy) -> None:
    plan = _plan()
    next_bar = _bar(date(2025, 1, 3), "101", "105", "98", "104")  # low 98 > stop 95
    fill = policy.fill_stop(plan, next_bar, adv=1_000_000, atr_pct=0.02)
    assert fill is None


def test_target_intra_bar_touch_fills_at_target(policy: FillPolicy) -> None:
    plan = _plan()
    next_bar = _bar(date(2025, 1, 4), "105", "112", "104", "111")  # high 112 >= T1 110
    fill = policy.fill_target(
        plan, next_bar, target_level=1, adv=1_000_000, atr_pct=0.02
    )
    assert fill is not None
    # touch fill near 110 with sell slippage
    assert fill.price < Decimal("110")


def test_target_gap_through_fills_at_open(policy: FillPolicy) -> None:
    plan = _plan()
    # gaps up through T2 120; opens at 125
    next_bar = _bar(date(2025, 1, 5), "125", "128", "124", "127")
    fill = policy.fill_target(
        plan, next_bar, target_level=2, adv=1_000_000, atr_pct=0.02
    )
    assert fill is not None
    # gap-through fills at open (125) minus slippage, not at target 120
    assert fill.price > Decimal("120")


def test_target_not_reached_returns_none(policy: FillPolicy) -> None:
    plan = _plan()
    next_bar = _bar(date(2025, 1, 4), "105", "108", "104", "107")  # high 108 < T1 110
    fill = policy.fill_target(
        plan, next_bar, target_level=1, adv=1_000_000, atr_pct=0.02
    )
    assert fill is None
