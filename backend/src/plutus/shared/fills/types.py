from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class OHLCBar:
    as_of: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class TradePlan:
    """Minimal fill-relevant view of a signal/trade.

    Decoupled from the ORM so the fill policy stays a pure function of price geometry.
    """

    symbol: str
    signal_date: date
    entry: Decimal
    stop_loss: Decimal
    target_1: Decimal
    target_2: Decimal
