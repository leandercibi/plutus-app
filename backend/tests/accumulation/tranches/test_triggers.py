from __future__ import annotations

from decimal import Decimal

import pytest

from plutus.accumulation.tranches.triggers import ATRNormalizedTrigger


@pytest.fixture
def trigger() -> ATRNormalizedTrigger:
    return ATRNormalizedTrigger()


def test_trigger_drop_scales_with_seq(trigger: ATRNormalizedTrigger) -> None:
    last = Decimal("100")
    atr_pct = 0.02  # 2%
    p2 = trigger.next_trigger_price(last, atr_pct, tranche_seq=2)
    p3 = trigger.next_trigger_price(last, atr_pct, tranche_seq=3)
    p5 = trigger.next_trigger_price(last, atr_pct, tranche_seq=5)
    # later tranches trigger further below the last fill
    assert p2 > p3 > p5


def test_k_schedule_values(trigger: ATRNormalizedTrigger) -> None:
    last = Decimal("100")
    atr_pct = 0.02
    # seq2 = 1.5 ATR drop = 3% -> 97; seq3 = 2.5 ATR = 5% -> 95; seq5 = 5 ATR = 10% -> 90
    assert trigger.next_trigger_price(last, atr_pct, 2) == pytest.approx(Decimal("97"))
    assert trigger.next_trigger_price(last, atr_pct, 3) == pytest.approx(Decimal("95"))
    assert trigger.next_trigger_price(last, atr_pct, 4) == pytest.approx(Decimal("93"))
    assert trigger.next_trigger_price(last, atr_pct, 5) == pytest.approx(Decimal("90"))


@pytest.mark.hallmark
def test_atr_normalized_not_fixed_drop() -> None:
    """A13 hallmark: same tranche seq produces DIFFERENT absolute % drops for
    low-ATR vs high-ATR stocks. Higher ATR -> wider drop (never the fixed -8/-15)."""
    trigger = ATRNormalizedTrigger()
    last = Decimal("100")

    low_atr = 0.01  # 1% ATR (FMCG-like)
    high_atr = 0.05  # 5% ATR (high-beta smallcap)

    seq = 3
    low_price = trigger.next_trigger_price(last, low_atr, seq)
    high_price = trigger.next_trigger_price(last, high_atr, seq)

    low_drop_pct = float((last - low_price) / last)
    high_drop_pct = float((last - high_price) / last)

    # the two are NOT the same fixed percentage
    assert low_drop_pct != high_drop_pct
    # higher ATR triggers a wider drop
    assert high_drop_pct > low_drop_pct
    # low-ATR drop is tightly spaced (seq3 = 2.5 * 1% = 2.5%)
    assert low_drop_pct == pytest.approx(0.025)
    # high-ATR drop is wide (seq3 = 2.5 * 5% = 12.5%)
    assert high_drop_pct == pytest.approx(0.125)


def test_invalid_seq_raises(trigger: ATRNormalizedTrigger) -> None:
    with pytest.raises(ValueError):
        trigger.next_trigger_price(Decimal("100"), 0.02, tranche_seq=1)
    with pytest.raises(ValueError):
        trigger.next_trigger_price(Decimal("100"), 0.02, tranche_seq=6)
