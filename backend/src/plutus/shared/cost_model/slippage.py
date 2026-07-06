from __future__ import annotations

from decimal import Decimal
from typing import Literal

from plutus.config.settings import Settings

_K_SIZE = 10.0
_K_VOL = 8.0
_BPS_PER_UNIT = Decimal("0.0001")


class SlippageModel:
    def __init__(self, settings: Settings) -> None:
        self._base = settings.slippage_bps_base

    def slippage_bps(self, qty: int, adv_20d: int, atr_pct: float) -> float:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if adv_20d <= 0:
            raise ValueError("adv_20d must be positive")
        position_pct_of_adv = qty / adv_20d
        return self._base * (1 + position_pct_of_adv * _K_SIZE) * (1 + atr_pct * _K_VOL)

    def apply_to_price(self, price: Decimal, side: Literal["BUY", "SELL"], bps: float) -> Decimal:
        adjustment = price * Decimal(str(bps)) * _BPS_PER_UNIT
        if side == "BUY":
            return price + adjustment
        return price - adjustment
