from __future__ import annotations

from datetime import datetime
from decimal import Decimal

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


def _bull() -> RegimeVerdict:
    return RegimeVerdict(label="BULL", confidence="high", reasons=[], breadth_confirmed=True)


def test_auto_convert_off_by_default() -> None:
    converter = BullReadyConverter()
    assert converter.auto_convert is False


def test_offer_does_not_mutate_position_state() -> None:
    """Voluntary: the converter only OFFERS; it never auto-flips the position state.

    The operator must confirm before any state transition to CONVERTED_TO_SWING.
    """
    converter = BullReadyConverter()
    position = _position()
    outcome = converter.evaluate(position, _bull(), object())
    assert outcome.offer is True
    # state is untouched — no auto conversion
    assert position.state == "FULL"


def test_auto_convert_flag_can_be_enabled_explicitly() -> None:
    converter = BullReadyConverter(auto_convert=True)
    assert converter.auto_convert is True
