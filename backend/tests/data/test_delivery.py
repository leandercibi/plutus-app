from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from plutus.data.delivery import (
    delivery_adjusted_volume,
    fetch_delivery,
    is_expiry_or_rebalance_day,
)


class _StubDelivery:
    name = "nse"

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        return self._df.copy()


def test_delivery_pct_clipped_to_unit_range() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    raw = pd.DataFrame(
        {
            "delivery_qty": [
                500,
                1500,
                0,
            ],  # middle row impossible (>traded) -> clip to 1
            "traded_qty": [1000, 1000, 1000],
        },
        index=idx,
    )
    provider = _StubDelivery(raw)
    out = fetch_delivery("INFY", date(2025, 1, 1), date(2025, 1, 3), provider)
    assert out["delivery_pct"].min() >= 0.0
    assert out["delivery_pct"].max() <= 1.0
    assert out["delivery_pct"].iloc[0] == 0.5


def test_missing_day_becomes_nan_not_zero() -> None:
    idx = pd.date_range("2025-01-01", periods=2, freq="D")
    raw = pd.DataFrame(
        {"delivery_qty": [500, np.nan], "traded_qty": [1000, np.nan]}, index=idx
    )
    provider = _StubDelivery(raw)
    out = fetch_delivery("INFY", date(2025, 1, 1), date(2025, 1, 2), provider)
    assert np.isnan(out["delivery_pct"].iloc[1])


def test_delivery_adjusted_volume_is_traded_times_pct() -> None:
    traded = pd.Series([1000, 2000, 3000])
    pct = pd.Series([0.5, 0.25, 1.0])
    adj = delivery_adjusted_volume(traded, pct)
    assert list(adj) == [500.0, 500.0, 3000.0]


def test_is_expiry_day_for_last_thursday_of_month() -> None:
    # 2025-01-30 is the last Thursday of January 2025 -> monthly expiry
    assert is_expiry_or_rebalance_day(date(2025, 1, 30)) is True


def test_non_expiry_day_returns_false() -> None:
    assert is_expiry_or_rebalance_day(date(2025, 1, 15)) is False
