from __future__ import annotations

from decimal import Decimal

import pytest

from plutus.config.settings import Settings
from plutus.shared.cost_model.slippage import SlippageModel


@pytest.fixture
def model() -> SlippageModel:
    return SlippageModel(Settings(_env_file=None))


def test_larger_position_pct_of_adv_increases_bps(model: SlippageModel) -> None:
    small = model.slippage_bps(qty=100, adv_20d=1_000_000, atr_pct=0.02)
    large = model.slippage_bps(qty=100_000, adv_20d=1_000_000, atr_pct=0.02)
    assert large > small


def test_higher_atr_pct_increases_bps(model: SlippageModel) -> None:
    low = model.slippage_bps(qty=100, adv_20d=1_000_000, atr_pct=0.01)
    high = model.slippage_bps(qty=100, adv_20d=1_000_000, atr_pct=0.05)
    assert high > low


def test_zero_adv_raises(model: SlippageModel) -> None:
    with pytest.raises(ValueError):
        model.slippage_bps(qty=100, adv_20d=0, atr_pct=0.02)


def test_negative_qty_raises(model: SlippageModel) -> None:
    with pytest.raises(ValueError):
        model.slippage_bps(qty=-1, adv_20d=1_000_000, atr_pct=0.02)


def test_buy_increases_price(model: SlippageModel) -> None:
    out = model.apply_to_price(Decimal("100"), "BUY", 50.0)
    assert out > Decimal("100")


def test_sell_decreases_price(model: SlippageModel) -> None:
    out = model.apply_to_price(Decimal("100"), "SELL", 50.0)
    assert out < Decimal("100")


def test_slippage_never_zero_or_negative_for_nontrivial_input(
    model: SlippageModel,
) -> None:
    bps = model.slippage_bps(qty=1, adv_20d=1_000_000, atr_pct=0.0)
    assert bps >= model._base
    assert bps > 0
