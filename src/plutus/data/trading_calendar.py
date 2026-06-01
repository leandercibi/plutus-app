# src/plutus/data/trading_calendar.py
from pathlib import Path
from datetime import date, timedelta
from plutus.config import settings


_HOLIDAYS_CACHE = None

def _load_holidays() -> set[date]:
    global _HOLIDAYS_CACHE
    if _HOLIDAYS_CACHE is not None:
        return _HOLIDAYS_CACHE
    p = Path(settings.NSE_HOLIDAYS_FILE)
    if not p.exists():
        _HOLIDAYS_CACHE = set()
        return _HOLIDAYS_CACHE
    _HOLIDAYS_CACHE = {date.fromisoformat(line.strip())
                       for line in p.read_text().splitlines()
                       if line.strip() and not line.startswith("#")}
    return _HOLIDAYS_CACHE


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _load_holidays()


def nse_trading_days_between(start: date, end: date) -> int:
    """Count NSE trading days strictly between start (exclusive) and end (inclusive)."""
    if end <= start:
        return 0
    days = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if is_trading_day(cur):
            days += 1
        cur += timedelta(days=1)
    return days
