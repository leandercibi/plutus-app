from __future__ import annotations

from datetime import date

from plutus.data.earnings_calendar import (
    fetch_earnings_dates,
    is_earnings_in_window,
)


class _StubEarnings:
    def __init__(self, mapping: dict[str, list[date]]) -> None:
        self._mapping = mapping

    def fetch(self, symbol: str, lookahead_days: int) -> list[date]:
        return list(self._mapping.get(symbol, []))


def test_fetch_returns_provider_dates() -> None:
    provider = _StubEarnings({"INFY": [date(2025, 1, 15)]})
    dates = fetch_earnings_dates("INFY", provider=provider, lookahead_days=60)
    assert dates == [date(2025, 1, 15)]


def test_unknown_symbol_returns_empty_list_not_error() -> None:
    provider = _StubEarnings({})
    dates = fetch_earnings_dates("UNKNOWN", provider=provider)
    assert dates == []


def test_is_earnings_in_window_true_when_date_inside() -> None:
    provider = _StubEarnings({"INFY": [date(2025, 1, 20)]})
    assert (
        is_earnings_in_window("INFY", date(2025, 1, 1), date(2025, 1, 31), provider=provider)
        is True
    )


def test_is_earnings_in_window_false_when_outside() -> None:
    provider = _StubEarnings({"INFY": [date(2025, 2, 20)]})
    assert (
        is_earnings_in_window("INFY", date(2025, 1, 1), date(2025, 1, 31), provider=provider)
        is False
    )


def test_is_earnings_in_window_inclusive_bounds() -> None:
    provider = _StubEarnings({"INFY": [date(2025, 1, 31)]})
    assert (
        is_earnings_in_window("INFY", date(2025, 1, 1), date(2025, 1, 31), provider=provider)
        is True
    )


def test_unknown_symbol_window_is_false() -> None:
    provider = _StubEarnings({})
    assert (
        is_earnings_in_window("UNKNOWN", date(2025, 1, 1), date(2025, 1, 31), provider=provider)
        is False
    )
