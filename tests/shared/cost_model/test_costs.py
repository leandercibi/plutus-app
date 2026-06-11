from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from plutus.config.settings import Settings
from plutus.shared.cost_model.costs import CostModel

_GRID = json.loads(
    (Path(__file__).parents[2] / "fixtures" / "cost_grid.json").read_text()
)


@pytest.fixture
def model() -> CostModel:
    return CostModel(Settings(_env_file=None))


def test_buy_cost_matches_grid_to_the_paisa(model: CostModel) -> None:
    for case in _GRID["buy"]:
        b = model.buy_cost(case["qty"], Decimal(case["price"]))
        assert b.brokerage == Decimal(case["brokerage"])
        assert b.stt == Decimal(case["stt"])
        assert b.exchange == Decimal(case["exchange"])
        assert b.gst == Decimal(case["gst"])
        assert b.stamp_duty == Decimal(case["stamp_duty"])
        assert b.total == Decimal(case["total"])


def test_sell_cost_matches_grid(model: CostModel) -> None:
    for case in _GRID["sell"]:
        s = model.sell_cost(case["qty"], Decimal(case["price"]))
        assert s.total == Decimal(case["total"])
        # stamp duty is buy-side only
        assert s.stamp_duty == Decimal("0.0000")


def test_brokerage_capped_at_flat_fee_for_large_notional(model: CostModel) -> None:
    b = model.buy_cost(100, Decimal("1000"))  # 0.03% of 100000 = 30 > 20 cap
    assert b.brokerage == Decimal("20.0000")


def test_brokerage_uses_pct_for_small_notional(model: CostModel) -> None:
    b = model.buy_cost(10, Decimal("100"))  # 0.03% of 1000 = 0.30 < 20
    assert b.brokerage == Decimal("0.3000")


def test_stt_applied_both_legs(model: CostModel) -> None:
    buy = model.buy_cost(100, Decimal("1000"))
    sell = model.sell_cost(100, Decimal("1000"))
    assert buy.stt == Decimal("100.0000")
    assert sell.stt == Decimal("100.0000")


def test_gst_only_on_brokerage_and_exchange(model: CostModel) -> None:
    b = model.buy_cost(100, Decimal("1000"))
    expected_gst = (b.brokerage + b.exchange) * Decimal("0.18")
    assert b.gst == expected_gst.quantize(Decimal("0.0001"))


def test_round_trip_cost_is_buy_plus_sell(model: CostModel) -> None:
    rt = model.round_trip_cost(100, Decimal("1000"), Decimal("1100"))
    buy = model.buy_cost(100, Decimal("1000")).total
    sell = model.sell_cost(100, Decimal("1100")).total
    assert rt == buy + sell
