from __future__ import annotations

from datetime import date

import pandas as pd

from plutus.data.base import AdjustmentPolicy
from plutus.data.ohlcv import OHLCVChain, OHLCVResult


class _StubProvider:
    def __init__(
        self,
        name: str,
        df: pd.DataFrame | None,
        adjustment: AdjustmentPolicy = "split_and_dividend",
    ) -> None:
        self.name = name
        self.adjustment = adjustment
        self._df = df
        self.calls = 0

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        self.calls += 1
        if self._df is None:
            raise RuntimeError(f"{self.name} provider down")
        return self._df.copy()


def _frame(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1000] * len(closes),
        },
        index=idx,
    )


def test_primary_success_fetches_fallback_overlap_for_reconciliation() -> None:
    primary = _StubProvider("yfinance", _frame([100.0, 101.0, 102.0]))
    fallback = _StubProvider("nse", _frame([100.1, 101.1, 102.1]))
    chain = OHLCVChain(primary, fallback)
    result = chain.fetch("INFY", date(2025, 1, 1), date(2025, 1, 3))
    assert isinstance(result, OHLCVResult)
    assert result.success is True
    assert result.source == "yfinance"
    assert result.fallback_used is False
    assert result.reconciliation_warning is False
    assert fallback.calls == 1  # overlap fetch happened


def test_reconciliation_warning_flagged_on_large_diff() -> None:
    primary = _StubProvider("yfinance", _frame([100.0, 101.0, 102.0]))
    fallback = _StubProvider("nse", _frame([100.0, 101.0, 110.0]))  # ~7.8% on last
    chain = OHLCVChain(primary, fallback)
    result = chain.fetch("INFY", date(2025, 1, 1), date(2025, 1, 3))
    assert result.success is True
    assert result.reconciliation_warning is True


def test_primary_fail_falls_back_fully_and_flags() -> None:
    primary = _StubProvider("yfinance", None)
    fallback = _StubProvider("nse", _frame([100.0, 101.0]))
    chain = OHLCVChain(primary, fallback)
    result = chain.fetch("INFY", date(2025, 1, 1), date(2025, 1, 2))
    assert result.success is True
    assert result.source == "nse"
    assert result.fallback_used is True


def test_both_fail_returns_success_false() -> None:
    primary = _StubProvider("yfinance", None)
    fallback = _StubProvider("nse", None)
    chain = OHLCVChain(primary, fallback)
    result = chain.fetch("INFY", date(2025, 1, 1), date(2025, 1, 2))
    assert result.success is False
    assert result.df is None


def test_no_fallback_primary_only() -> None:
    primary = _StubProvider("yfinance", _frame([100.0, 101.0]))
    chain = OHLCVChain(primary, None)
    result = chain.fetch("INFY", date(2025, 1, 1), date(2025, 1, 2))
    assert result.success is True
    assert result.source == "yfinance"
    assert result.reconciliation_warning is False


def test_cache_hit_short_circuits(tmp_path) -> None:  # type: ignore[no-untyped-def]
    primary = _StubProvider("yfinance", _frame([100.0, 101.0]))
    chain = OHLCVChain(primary, None, cache_dir=tmp_path, cache_ttl_hours=6)
    chain.fetch("INFY", date(2025, 1, 1), date(2025, 1, 2))
    assert primary.calls == 1
    # second fetch with same window: served from cache, provider not called again
    chain.fetch("INFY", date(2025, 1, 1), date(2025, 1, 2))
    assert primary.calls == 1


def test_cache_ttl_expiry_refetches(tmp_path) -> None:  # type: ignore[no-untyped-def]
    primary = _StubProvider("yfinance", _frame([100.0, 101.0]))
    chain = OHLCVChain(primary, None, cache_dir=tmp_path, cache_ttl_hours=0)
    chain.fetch("INFY", date(2025, 1, 1), date(2025, 1, 2))
    chain.fetch("INFY", date(2025, 1, 1), date(2025, 1, 2))
    assert primary.calls == 2  # TTL 0 -> always stale -> refetch
