from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal
from plutus.swing.entries.monday_revalidation import (
    MondayRevalidation,
    RevalidationOutcome,
)


def _signal(entry: str = "100") -> BundleSignal:
    return BundleSignal(
        symbol="INFY",
        bundle="trend",
        as_of=date(2025, 1, 1),
        entry=Decimal(entry),
        stop_loss=Decimal("95"),
        target_1=Decimal("110"),
        target_2=Decimal("120"),
    )


@pytest.fixture
def reval() -> MondayRevalidation:
    return MondayRevalidation(Settings(_env_file=None))


def test_weekend_gap_greater_than_one_atr_kills(reval: MondayRevalidation) -> None:
    # entry 100, monday open 103, atr 2 -> gap 3 > 1*2 -> kill
    out = reval.reevaluate(
        _signal(), monday_open=Decimal("103"), atr=Decimal("2"), hard_kill_fires=False
    )
    assert isinstance(out, RevalidationOutcome)
    assert out.keep is False
    assert "gap" in out.reason.lower()


def test_hard_kill_sentiment_kills(reval: MondayRevalidation) -> None:
    # small gap, but a corroborated weekend hard-kill -> kill
    out = reval.reevaluate(
        _signal(), monday_open=Decimal("100.5"), atr=Decimal("2"), hard_kill_fires=True
    )
    assert out.keep is False
    assert "hard" in out.reason.lower() or "kill" in out.reason.lower()


def test_clean_monday_keeps(reval: MondayRevalidation) -> None:
    # gap 1 <= 1*2, no hard kill -> keep
    out = reval.reevaluate(
        _signal(), monday_open=Decimal("101"), atr=Decimal("2"), hard_kill_fires=False
    )
    assert out.keep is True


def test_gap_exactly_one_atr_is_not_killed(reval: MondayRevalidation) -> None:
    # gap 2 == 1*2 -> not strictly greater -> keep
    out = reval.reevaluate(
        _signal(), monday_open=Decimal("102"), atr=Decimal("2"), hard_kill_fires=False
    )
    assert out.keep is True


def test_gap_down_also_kills(reval: MondayRevalidation) -> None:
    # gap-down 100 -> 96 = 4 > 1*2 -> kill (absolute gap)
    out = reval.reevaluate(
        _signal(), monday_open=Decimal("96"), atr=Decimal("2"), hard_kill_fires=False
    )
    assert out.keep is False
