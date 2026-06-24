from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class BulkBlockEvent:
    symbol: str
    date: date
    qty: int
    value_inr: Decimal
    buyer: str
    seller: str


class BulkBlockProvider(Protocol):
    def fetch(self, symbol: str, start: date, end: date) -> list[BulkBlockEvent]: ...


def fetch_bulk_block(
    symbol: str, start: date, end: date, provider: BulkBlockProvider
) -> list[BulkBlockEvent]:
    """Bulk/block deal events for a symbol in [start, end].

    Consumed by shared/smart_money/ (never used as a regime input). Unknown
    symbol -> empty list.
    """
    return provider.fetch(symbol, start, end)
