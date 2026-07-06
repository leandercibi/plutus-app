from __future__ import annotations

from datetime import date
from typing import ClassVar, Literal, Protocol, runtime_checkable

import pandas as pd

AdjustmentPolicy = Literal["adjusted_close_only", "split_adjusted", "split_and_dividend"]


@runtime_checkable
class OHLCVProvider(Protocol):
    name: ClassVar[str]
    adjustment: ClassVar[AdjustmentPolicy]

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Return columns: open, high, low, close, volume; indexed by date."""
        ...


@runtime_checkable
class DeliveryProvider(Protocol):
    name: str

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Return columns: delivery_qty, traded_qty, delivery_pct; indexed by date."""
        ...
