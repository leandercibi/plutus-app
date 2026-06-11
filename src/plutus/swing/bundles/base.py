from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Literal

import pandas as pd

from plutus.shared.types import BundleSignal

RequiredInput = Literal["ohlcv", "delivery", "bulk_block", "earnings"]


@dataclass(frozen=True)
class BundleContext:
    """Per-symbol inputs available to a bundle at fit time.

    `delivery` carries delivery-adjusted volume (A9). All frames are date-indexed
    or carry a 'date' column; bundles read the last row as 'today'.
    """

    symbol: str
    regime: str
    delivery: pd.DataFrame | None = None
    bulk_block: pd.DataFrame | None = None
    earnings_in_window: bool = False
    extras: dict[str, object] = field(default_factory=dict)


class BaseBundle(ABC):
    name: ClassVar[str]
    horizon_days: ClassVar[tuple[int, int]]

    @abstractmethod
    def fit_signal(
        self, symbol: str, candles: pd.DataFrame, ctx: BundleContext
    ) -> BundleSignal | None:
        """Return a candidate signal, or None when there is no setup today."""

    @abstractmethod
    def required_inputs(self) -> set[RequiredInput]: ...
