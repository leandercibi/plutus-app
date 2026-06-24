from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd


class VixProvider(Protocol):
    def fetch(self, start: date, end: date) -> pd.Series: ...


def fetch_india_vix(start: date, end: date, provider: VixProvider) -> pd.Series:
    """India VIX series, sorted by date (B13)."""
    return provider.fetch(start, end).sort_index()


def latest_india_vix(start: date, end: date, provider: VixProvider) -> float:
    return float(fetch_india_vix(start, end, provider).iloc[-1])
