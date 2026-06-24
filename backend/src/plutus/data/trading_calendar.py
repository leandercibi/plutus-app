from __future__ import annotations

from datetime import date, timedelta

# NSE trading holidays for 2025 (hardcoded yearly file per spec §8).
# Manual additions for unscheduled holidays are appended here.
_NSE_HOLIDAYS_2025: frozenset[date] = frozenset(
    {
        date(2025, 2, 26),  # Mahashivratri
        date(2025, 3, 14),  # Holi
        date(2025, 3, 31),  # Id-Ul-Fitr (Ramzan Id)
        date(2025, 4, 10),  # Mahavir Jayanti
        date(2025, 4, 14),  # Dr. Ambedkar Jayanti
        date(2025, 4, 18),  # Good Friday
        date(2025, 5, 1),  # Maharashtra Day
        date(2025, 8, 15),  # Independence Day
        date(2025, 8, 27),  # Ganesh Chaturthi
        date(2025, 10, 2),  # Gandhi Jayanti / Dussehra
        date(2025, 10, 21),  # Diwali Laxmi Pujan
        date(2025, 10, 22),  # Diwali Balipratipada
        date(2025, 11, 5),  # Guru Nanak Jayanti
        date(2025, 12, 25),  # Christmas
    }
)

_HOLIDAYS: frozenset[date] = _NSE_HOLIDAYS_2025

_SATURDAY = 5


def is_trading_day(d: date) -> bool:
    if d.weekday() >= _SATURDAY:
        return False
    return d not in _HOLIDAYS


def last_trading_day(on_or_before: date) -> date:
    d = on_or_before
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def next_trading_day(on_or_after: date) -> date:
    d = on_or_after
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def trading_days_between(start: date, end: date) -> list[date]:
    days: list[date] = []
    d = start
    while d <= end:
        if is_trading_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days
