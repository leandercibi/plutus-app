from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from plutus.accumulation.bull_ready.converter import BullReadyConverter
from plutus.db.models import AccumulationPosition
from plutus.shared.regime.detector import RegimeVerdict


def _position() -> AccumulationPosition:
    return AccumulationPosition(
        symbol="TCS",
        state="FULL",
        avg_cost=Decimal("100"),
        qty_total=10000,
        opened_at=datetime(2024, 1, 1),
        last_thesis_check_at=datetime(2024, 6, 1),
    )


def _bull(breadth_confirmed: bool) -> RegimeVerdict:
    return RegimeVerdict(
        label="BULL",
        confidence="high",
        reasons=["nifty > 200dma"],
        breadth_confirmed=breadth_confirmed,
    )


@pytest.fixture
def converter() -> BullReadyConverter:
    return BullReadyConverter()


def test_bull_with_breadth_and_setup_offers_conversion(
    converter: BullReadyConverter,
) -> None:
    setup = object()  # opaque truthy swing setup
    outcome = converter.evaluate(_position(), _bull(breadth_confirmed=True), setup)
    assert outcome.offer is True


def test_no_breadth_no_offer(converter: BullReadyConverter) -> None:
    setup = object()
    outcome = converter.evaluate(_position(), _bull(breadth_confirmed=False), setup)
    assert outcome.offer is False


def test_no_swing_setup_no_offer(converter: BullReadyConverter) -> None:
    outcome = converter.evaluate(_position(), _bull(breadth_confirmed=True), None)
    assert outcome.offer is False


def test_non_bull_regime_no_offer(converter: BullReadyConverter) -> None:
    bear = RegimeVerdict(
        label="BEAR", confidence="high", reasons=[], breadth_confirmed=True
    )
    outcome = converter.evaluate(_position(), bear, object())
    assert outcome.offer is False
