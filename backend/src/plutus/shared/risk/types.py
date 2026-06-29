from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpenPosition:
    symbol: str
    sector: str
    risk_R: float
    position_value_inr: float | None = None
