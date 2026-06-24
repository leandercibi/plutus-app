from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from plutus.config.settings import Settings


class _Signal(Protocol):
    symbol: str


class ADVCap:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def max_position_qty(self, symbol: str, price: Decimal, adv_20d_qty: int) -> int:
        return int(adv_20d_qty * self._settings.max_position_pct_of_adv)

    def annotate(self, signal: _Signal, qty: int, adv_20d_qty: int) -> str:
        return f"position = {qty / adv_20d_qty:.1%} of 20d ADV"
