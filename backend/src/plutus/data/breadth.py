from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd


class BreadthProvider(Protocol):
    def fetch_pct_above_dma(self, window: int, start: date, end: date) -> pd.Series: ...

    def fetch_advance_decline(self, start: date, end: date) -> pd.Series: ...


def fetch_pct_above_dma(
    window: int, start: date, end: date, provider: BreadthProvider
) -> pd.Series:
    """Series of fraction of universe above the N-day moving average (B13)."""
    return provider.fetch_pct_above_dma(window, start, end).clip(lower=0.0, upper=1.0)


def fetch_advance_decline(start: date, end: date, provider: BreadthProvider) -> pd.Series:
    """Daily advance/decline ratio. >1 means advancers dominate."""
    return provider.fetch_advance_decline(start, end)


def latest_pct_above_dma(window: int, start: date, end: date, provider: BreadthProvider) -> float:
    series = fetch_pct_above_dma(window, start, end, provider)
    return float(series.iloc[-1])
