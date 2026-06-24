from __future__ import annotations

from datetime import date

from plutus.config.settings import get_settings
from plutus.data.trading_calendar import last_trading_day


class FreshnessError(RuntimeError):
    """Raised when the latest available candle is not the last trading day (B11).

    A stale candle invalidates an entire run; the scheduler aborts on this.
    """


def assert_freshness(
    latest_candle_date: date, run_date: date, enabled: bool | None = None
) -> None:
    """Raise FreshnessError if latest_candle_date != last_trading_day(run_date).

    Honors settings.freshness_assert_enabled when `enabled` is not given.
    """
    if enabled is None:
        enabled = get_settings().freshness_assert_enabled
    if not enabled:
        return
    expected = last_trading_day(run_date)
    if latest_candle_date != expected:
        raise FreshnessError(
            f"stale data: latest candle {latest_candle_date.isoformat()} "
            f"!= last trading day {expected.isoformat()} for run {run_date.isoformat()}"
        )
