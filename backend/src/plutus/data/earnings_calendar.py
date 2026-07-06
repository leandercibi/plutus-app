from __future__ import annotations

from datetime import date
from typing import Protocol


class EarningsProvider(Protocol):
    def fetch(self, symbol: str, lookahead_days: int) -> list[date]: ...


def fetch_earnings_dates(
    symbol: str, provider: EarningsProvider, lookahead_days: int = 60
) -> list[date]:
    """Best-effort earnings dates. Unknown symbol -> empty list (B6)."""
    return provider.fetch(symbol, lookahead_days)


def is_earnings_in_window(symbol: str, start: date, end: date, provider: EarningsProvider) -> bool:
    """True if any earnings date falls within [start, end] inclusive (B6)."""
    dates = fetch_earnings_dates(symbol, provider, lookahead_days=(end - start).days + 1)
    return any(start <= d <= end for d in dates)
