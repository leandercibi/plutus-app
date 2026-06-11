from __future__ import annotations

from datetime import date

from plutus.data.trading_calendar import (
    is_trading_day,
    last_trading_day,
    next_trading_day,
    trading_days_between,
)


def test_weekend_is_not_a_trading_day() -> None:
    # 2025-01-04 is a Saturday, 2025-01-05 a Sunday
    assert is_trading_day(date(2025, 1, 4)) is False
    assert is_trading_day(date(2025, 1, 5)) is False


def test_known_nse_holiday_is_not_a_trading_day() -> None:
    # 2025-01-26 Republic Day (Sunday anyway); 2025-08-15 Independence Day (Friday)
    assert is_trading_day(date(2025, 8, 15)) is False
    # 2025-10-02 Gandhi Jayanti (Thursday)
    assert is_trading_day(date(2025, 10, 2)) is False


def test_regular_weekday_is_a_trading_day() -> None:
    # 2025-01-06 is a Monday, not a holiday
    assert is_trading_day(date(2025, 1, 6)) is True


def test_last_trading_day_of_saturday_is_previous_friday() -> None:
    # 2025-01-04 Saturday -> 2025-01-03 Friday (a trading day)
    assert last_trading_day(date(2025, 1, 4)) == date(2025, 1, 3)


def test_last_trading_day_on_a_trading_day_is_itself() -> None:
    assert last_trading_day(date(2025, 1, 6)) == date(2025, 1, 6)


def test_last_trading_day_skips_holiday_and_weekend() -> None:
    # 2025-08-16 Saturday, 2025-08-15 Independence Day, 2025-08-14 Thursday is a trading day
    assert last_trading_day(date(2025, 8, 16)) == date(2025, 8, 14)


def test_next_trading_day_skips_weekend() -> None:
    # 2025-01-03 Friday -> next is Monday 2025-01-06
    assert next_trading_day(date(2025, 1, 4)) == date(2025, 1, 6)


def test_next_trading_day_on_trading_day_is_itself() -> None:
    assert next_trading_day(date(2025, 1, 6)) == date(2025, 1, 6)


def test_trading_days_between_excludes_weekends_and_holidays() -> None:
    days = trading_days_between(date(2025, 8, 13), date(2025, 8, 18))
    # 13 Wed, 14 Thu trading; 15 Fri holiday; 16 Sat, 17 Sun weekend; 18 Mon trading
    assert days == [date(2025, 8, 13), date(2025, 8, 14), date(2025, 8, 18)]
