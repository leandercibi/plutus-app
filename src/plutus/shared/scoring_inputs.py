from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ExpectancyInputs:
    bundle: str
    regime: str
    entry: Decimal
    stop_loss: Decimal
    target_1: Decimal
    target_2: Decimal
    qty: int
