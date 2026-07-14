from __future__ import annotations

from plutus.shared.smart_money.per_stock_score import FlowScore, PerStockFlow
from tests.shared.smart_money._flow_inputs import bb, delivery, mf


def test_compose_returns_flow_score() -> None:
    out = PerStockFlow().compose(delivery(10), bb(8), mf("ACCUMULATING", 1.0), domain="swing")
    assert isinstance(out, FlowScore)
    assert 0 <= out.total_0_15 <= 15
    assert set(out.components) == {"delivery", "bulk_block", "mf"}


def test_swing_weights_delivery_dominates() -> None:
    out = PerStockFlow().compose(delivery(15), bb(15), mf("ACCUMULATING", 1.0), domain="swing")
    assert out.components["delivery"] > out.components["mf"]
    assert out.components["delivery"] > out.components["bulk_block"]
