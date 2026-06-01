"""Tests for plutus.data.trading_calendar module."""
import pytest
from datetime import date, timedelta
from pathlib import Path
from plutus.data import trading_calendar


class TestLoadHolidays:
    def test_loads_holidays_from_file(self, sample_holidays_file, monkeypatch):
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(sample_holidays_file))
        
        # Reset cache
        trading_calendar._HOLIDAYS_CACHE = None
        
        holidays = trading_calendar._load_holidays()
        
        assert len(holidays) == 3
        assert all(isinstance(h, date) for h in holidays)

    def test_returns_empty_set_for_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(tmp_path / "missing.txt"))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        holidays = trading_calendar._load_holidays()
        assert holidays == set()

    def test_ignores_comments_and_empty_lines(self, tmp_path, monkeypatch):
        holidays_file = tmp_path / "holidays.txt"
        holidays_file.write_text("""# Comment line
2026-06-01

2026-06-15
# Another comment
2026-07-01
""")
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        holidays = trading_calendar._load_holidays()
        assert len(holidays) == 3
        assert date(2026, 6, 1) in holidays
        assert date(2026, 6, 15) in holidays
        assert date(2026, 7, 1) in holidays

    def test_caches_holidays(self, sample_holidays_file, monkeypatch):
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(sample_holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        holidays1 = trading_calendar._load_holidays()
        holidays2 = trading_calendar._load_holidays()
        
        assert holidays1 is holidays2


class TestIsTradingDay:
    def test_weekday_not_holiday(self, tmp_path, monkeypatch):
        holidays_file = tmp_path / "holidays.txt"
        holidays_file.write_text("2026-12-25\n")
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        # Monday, not a holiday
        assert trading_calendar.is_trading_day(date(2026, 6, 1)) is True

    def test_saturday_is_not_trading_day(self, tmp_path, monkeypatch):
        holidays_file = tmp_path / "holidays.txt"
        holidays_file.write_text("")
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        # Saturday
        assert trading_calendar.is_trading_day(date(2026, 5, 30)) is False

    def test_sunday_is_not_trading_day(self, tmp_path, monkeypatch):
        holidays_file = tmp_path / "holidays.txt"
        holidays_file.write_text("")
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        # Sunday
        assert trading_calendar.is_trading_day(date(2026, 5, 31)) is False

    def test_holiday_is_not_trading_day(self, tmp_path, monkeypatch):
        holidays_file = tmp_path / "holidays.txt"
        holidays_file.write_text("2026-06-01\n")
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        # Monday but a holiday
        assert trading_calendar.is_trading_day(date(2026, 6, 1)) is False


class TestNseTradingDaysBetween:
    def test_counts_trading_days(self, tmp_path, monkeypatch):
        holidays_file = tmp_path / "holidays.txt"
        holidays_file.write_text("")
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        # Mon Jun 2 to Fri Jun 6 (5 weekdays, start exclusive, end inclusive)
        start = date(2026, 6, 1)  # Monday (exclusive)
        end = date(2026, 6, 5)    # Friday (inclusive)
        
        count = trading_calendar.nse_trading_days_between(start, end)
        assert count == 4  # Tue, Wed, Thu, Fri

    def test_excludes_weekends(self, tmp_path, monkeypatch):
        holidays_file = tmp_path / "holidays.txt"
        holidays_file.write_text("")
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        # Fri May 30 to Mon Jun 2 (includes Sat, Sun)
        start = date(2026, 5, 29)  # Friday (exclusive)
        end = date(2026, 6, 1)     # Monday (inclusive)
        
        count = trading_calendar.nse_trading_days_between(start, end)
        assert count == 1  # Only Monday

    def test_excludes_holidays(self, tmp_path, monkeypatch):
        holidays_file = tmp_path / "holidays.txt"
        holidays_file.write_text("2026-06-03\n")  # Wednesday
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        # Mon Jun 1 to Fri Jun 5
        start = date(2026, 6, 1)  # Monday (exclusive)
        end = date(2026, 6, 5)    # Friday (inclusive)
        
        count = trading_calendar.nse_trading_days_between(start, end)
        assert count == 3  # Tue, Thu, Fri (Wed is holiday)

    def test_returns_zero_when_end_before_start(self, tmp_path, monkeypatch):
        holidays_file = tmp_path / "holidays.txt"
        holidays_file.write_text("")
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        start = date(2026, 6, 5)
        end = date(2026, 6, 1)
        
        count = trading_calendar.nse_trading_days_between(start, end)
        assert count == 0

    def test_returns_zero_when_start_equals_end(self, tmp_path, monkeypatch):
        holidays_file = tmp_path / "holidays.txt"
        holidays_file.write_text("")
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        start = date(2026, 6, 1)
        end = date(2026, 6, 1)
        
        count = trading_calendar.nse_trading_days_between(start, end)
        assert count == 0

    def test_single_trading_day(self, tmp_path, monkeypatch):
        holidays_file = tmp_path / "holidays.txt"
        holidays_file.write_text("")
        monkeypatch.setattr("plutus.data.trading_calendar.settings.NSE_HOLIDAYS_FILE", str(holidays_file))
        
        trading_calendar._HOLIDAYS_CACHE = None
        
        # Monday to Tuesday
        start = date(2026, 6, 1)  # Monday (exclusive)
        end = date(2026, 6, 2)    # Tuesday (inclusive)
        
        count = trading_calendar.nse_trading_days_between(start, end)
        assert count == 1
