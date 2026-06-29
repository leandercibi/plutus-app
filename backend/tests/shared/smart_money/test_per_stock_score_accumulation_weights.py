from __future__ import annotations

from plutus.shared.smart_money.per_stock_score import PerStockFlow
from tests.shared.smart_money._flow_inputs import bb, delivery, mf


def test_accumulation_weights_mf_dominates() -> None:
    out = PerStockFlow().compose(
        delivery(15), bb(15), mf("ACCUMULATING", 1.0), domain="accumulation"
    )
    assert out.components["mf"] > out.components["delivery"]
    assert out.components["mf"] > out.components["bulk_block"]


def test_mf_confidence_decay_reduces_mf_contribution() -> None:
    full = PerStockFlow().compose(
        delivery(10), bb(10), mf("ACCUMULATING", 1.0), domain="accumulation"
    )
    decayed = PerStockFlow().compose(
        delivery(10), bb(10), mf("ACCUMULATING", 0.5), domain="accumulation"
    )
    assert decayed.components["mf"] < full.components["mf"]


def test_distributing_mf_contributes_zero() -> None:
    out = PerStockFlow().compose(
        delivery(10), bb(10), mf("DISTRIBUTING", 1.0), domain="accumulation"
    )
    assert out.components["mf"] == 0
