from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from plutus.config.settings import Settings
from plutus.shared.cost_model.costs import CostModel

_model = CostModel(Settings(_env_file=None))


@settings(derandomize=True, max_examples=100)
@given(
    qty=st.integers(min_value=1, max_value=100_000),
    price=st.decimals(min_value=Decimal("1"), max_value=Decimal("100000"), places=2),
)
def test_total_cost_always_positive(qty: int, price: Decimal) -> None:
    assert _model.buy_cost(qty, price).total > 0


@settings(derandomize=True, max_examples=100)
@given(
    price=st.decimals(min_value=Decimal("10"), max_value=Decimal("10000"), places=2),
    qty_a=st.integers(min_value=1, max_value=1000),
    extra=st.integers(min_value=1, max_value=1000),
)
def test_round_trip_cost_monotone_in_qty(
    price: Decimal, qty_a: int, extra: int
) -> None:
    smaller = _model.round_trip_cost(qty_a, price, price)
    larger = _model.round_trip_cost(qty_a + extra, price, price)
    assert larger >= smaller
