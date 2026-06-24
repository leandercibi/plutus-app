from __future__ import annotations

import pandas as pd

from plutus.data.reconciliation import ReconciliationReport, reconcile


def _frame(closes: list[float], volumes: list[int]) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": volumes,
        },
        index=idx,
    )


def test_close_within_tolerance_no_warning() -> None:
    primary = _frame([100.0, 101.0, 102.0], [1000, 1100, 1200])
    fallback = _frame([100.2, 100.9, 102.1], [1000, 1100, 1200])
    report = reconcile(primary, fallback, "yfinance", "nse")
    assert isinstance(report, ReconciliationReport)
    assert report.max_close_diff_pct < 1.0
    assert report.warnings == []


def test_close_diff_above_one_pct_warns() -> None:
    primary = _frame([100.0, 101.0, 102.0], [1000, 1100, 1200])
    fallback = _frame([100.0, 101.0, 105.0], [1000, 1100, 1200])  # ~2.9% on last
    report = reconcile(primary, fallback, "yfinance", "nse")
    assert report.max_close_diff_pct > 1.0
    assert report.warnings != []


def test_split_disagreement_detected() -> None:
    # primary shows a halving (split) at index 2; fallback does not -> ratio mismatch
    primary = _frame([200.0, 200.0, 100.0, 100.0], [1000, 1000, 2000, 2000])
    fallback = _frame([200.0, 200.0, 200.0, 200.0], [1000, 1000, 1000, 1000])
    report = reconcile(primary, fallback, "yfinance", "nse")
    assert report.split_disagreement is True


def test_volume_diff_reported() -> None:
    primary = _frame([100.0, 101.0], [1000, 1100])
    fallback = _frame([100.0, 101.0], [1000, 2200])  # 100% volume diff
    report = reconcile(primary, fallback, "yfinance", "nse")
    assert report.max_volume_diff_pct > 50.0
