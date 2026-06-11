from __future__ import annotations

from decimal import Decimal

import pytest

from plutus.config.settings import Settings
from plutus.shared.risk.adv_cap import ADVCap


class _Signal:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol


@pytest.fixture
def adv() -> ADVCap:
    return ADVCap(Settings(_env_file=None))


def test_max_qty_is_10pct_of_adv_at_defaults(adv: ADVCap) -> None:
    qty = adv.max_position_qty("INFY", Decimal("1500"), adv_20d_qty=1_000_000)
    assert qty == 100_000  # 10% of 1,000,000


def test_annotation_string_format(adv: ADVCap) -> None:
    text = adv.annotate(_Signal("INFY"), qty=100_000, adv_20d_qty=1_000_000)
    assert text == "position = 10.0% of 20d ADV"


def test_annotation_partial_pct(adv: ADVCap) -> None:
    text = adv.annotate(_Signal("TCS"), qty=53_000, adv_20d_qty=1_000_000)
    assert text == "position = 5.3% of 20d ADV"
