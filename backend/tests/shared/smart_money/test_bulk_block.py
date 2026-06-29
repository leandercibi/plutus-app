from __future__ import annotations

from datetime import date
from decimal import Decimal

from plutus.shared.smart_money.bulk_block import (
    BulkBlockEvent,
    BulkBlockScore,
    BulkBlockSignal,
)


def _event(
    d: date,
    qty: int,
    value: str,
    buyer: str,
    seller: str = "UNKNOWN",
) -> BulkBlockEvent:
    return BulkBlockEvent(
        date=d,
        qty=qty,
        value_inr=Decimal(value),
        buyer_class=buyer,
        seller_class=seller,
    )


def test_net_institutional_buying_scores_high() -> None:
    events = [
        _event(date(2025, 1, 2), 100_000, "50000000", "FOREIGN_INSTITUTION"),
        _event(date(2025, 1, 3), 80_000, "40000000", "DOMESTIC_INSTITUTION"),
        _event(date(2025, 1, 4), 60_000, "30000000", "MF"),
    ]
    out = BulkBlockSignal().compute(events)
    assert isinstance(out, BulkBlockScore)
    assert out.score_0_15 >= 10
    assert out.net_value_inr > 0


def test_promoter_selling_scores_low() -> None:
    events = [
        _event(date(2025, 1, 2), 100_000, "50000000", "INDIVIDUAL", seller="PROMOTER"),
        _event(date(2025, 1, 3), 90_000, "45000000", "INDIVIDUAL", seller="PROMOTER"),
    ]
    out = BulkBlockSignal().compute(events)
    assert out.score_0_15 <= 4


def test_no_events_is_neutral() -> None:
    out = BulkBlockSignal().compute([])
    assert out.score_0_15 == 0
    assert out.net_value_inr == Decimal("0")
    assert out.buyer_class == "UNKNOWN"


def test_lookback_window_excludes_old_events() -> None:
    recent = _event(date(2025, 1, 20), 100_000, "50000000", "FOREIGN_INSTITUTION")
    out = BulkBlockSignal().compute([recent], lookback_sessions=10)
    assert out.score_0_15 >= 10


def test_institutional_buy_beats_individual_buy() -> None:
    inst = [_event(date(2025, 1, 2), 100_000, "50000000", "MF")]
    indiv = [_event(date(2025, 1, 2), 100_000, "50000000", "INDIVIDUAL")]
    inst_score = BulkBlockSignal().compute(inst).score_0_15
    indiv_score = BulkBlockSignal().compute(indiv).score_0_15
    assert inst_score > indiv_score
