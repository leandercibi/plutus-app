from __future__ import annotations

from datetime import date

import pytest

from plutus.data.freshness import FreshnessError, assert_freshness


@pytest.mark.hallmark
def test_equal_to_last_trading_day_does_not_raise() -> None:
    # 2025-01-06 Monday is a trading day; run same day -> latest candle is that day
    assert_freshness(date(2025, 1, 6), date(2025, 1, 6), enabled=True)


def test_last_trading_day_resolved_over_weekend() -> None:
    # run on Saturday 2025-01-04; last trading day is Friday 2025-01-03
    assert_freshness(date(2025, 1, 3), date(2025, 1, 4), enabled=True)


@pytest.mark.hallmark
def test_off_by_one_raises() -> None:
    with pytest.raises(FreshnessError):
        assert_freshness(date(2025, 1, 5), date(2025, 1, 6), enabled=True)


def test_stale_candle_raises_with_context() -> None:
    with pytest.raises(FreshnessError) as exc:
        assert_freshness(date(2025, 1, 2), date(2025, 1, 6), enabled=True)
    assert "2025-01-06" in str(exc.value) or "2025-01-02" in str(exc.value)


@pytest.mark.hallmark
def test_disabled_does_not_raise_even_when_stale() -> None:
    assert_freshness(date(2024, 1, 1), date(2025, 1, 6), enabled=False)
