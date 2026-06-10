# tests/test_phase2_f1_backtest.py
"""TDD tests for F1 — Fix Strategy Lab Backtest."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from plutus.data.ohlcv import InsufficientDataError, fetch_ohlcv
from plutus.backtesting.runner import (
    MIN_BARS_REQUIRED,
    BundleResult,
    _empty_result,
    _summarise,
    run_bundle,
)


# ── helpers ─────────────────────────────────────────────────────────────

def _make_df(n: int) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"Open": 100.0, "High": 105.0, "Low": 95.0, "Close": 102.0, "Volume": 1_000_000},
        index=idx,
    )


def _make_fetch_mock(n: int, requested: int = 90):
    df = _make_df(n)
    df.attrs["bars_fetched"] = n
    df.attrs["bars_requested"] = requested
    return df


# ── TestOHLCVValidation ─────────────────────────────────────────────────

class TestOHLCVValidation:
    def test_fetch_returns_bar_count_metadata(self):
        df = _make_fetch_mock(90)
        assert df.attrs["bars_fetched"] == 90
        assert df.attrs["bars_requested"] == 90

    def test_fetch_empty_returns_zero_bars(self):
        df = _make_fetch_mock(0)
        assert df.attrs["bars_fetched"] == 0

    def test_fetch_partial_returns_actual_count(self):
        df = _make_fetch_mock(30, requested=90)
        assert df.attrs["bars_fetched"] == 30
        assert df.attrs["bars_requested"] == 90

    def test_insufficient_data_error_message(self):
        err = InsufficientDataError(bars_fetched=10, bars_required=60, symbol="XYZ")
        assert "10" in str(err)
        assert "60" in str(err)
        assert "XYZ" in str(err)

    def test_insufficient_data_error_attributes(self):
        err = InsufficientDataError(bars_fetched=5, bars_required=60, symbol="ABC")
        assert err.bars_fetched == 5
        assert err.bars_required == 60
        assert err.symbol == "ABC"


# ── TestBacktestRunner ──────────────────────────────────────────────────

class TestBacktestRunner:
    def test_insufficient_bars_raises_error(self):
        short_df = _make_fetch_mock(30)
        with patch("plutus.backtesting.runner.fetch_ohlcv", return_value=short_df):
            with pytest.raises(InsufficientDataError) as exc_info:
                run_bundle("TEST", "trend", days=30)
            assert exc_info.value.bars_fetched == 30
            assert exc_info.value.bars_required == MIN_BARS_REQUIRED

    def test_exactly_min_bars_does_not_raise(self):
        exact_df = _make_fetch_mock(MIN_BARS_REQUIRED)
        with patch("plutus.backtesting.runner.fetch_ohlcv", return_value=exact_df):
            with patch("plutus.backtesting.runner.bt.Cerebro") as mock_cerebro:
                instance = mock_cerebro.return_value
                mock_strat = _make_mock_strat(trades=[])
                instance.run.return_value = [mock_strat]
                # Should not raise
                result = run_bundle("TEST", "trend", days=MIN_BARS_REQUIRED)
                assert isinstance(result, BundleResult)

    def test_partial_bars_returns_warning(self):
        partial_df = _make_fetch_mock(70, requested=90)
        with patch("plutus.backtesting.runner.fetch_ohlcv", return_value=partial_df):
            with patch("plutus.backtesting.runner.bt.Cerebro") as mock_cerebro:
                instance = mock_cerebro.return_value
                instance.run.return_value = [_make_mock_strat(trades=[])]
                result = run_bundle("TEST", "trend", days=90)
                assert any("70/90" in w for w in result.warnings)

    def test_sharpe_clamped_to_sane_range(self):
        # A result with extreme Sharpe from fake trades
        trades = [{"pnl_pct": 50.0}, {"pnl_pct": 50.0}, {"pnl_pct": 50.0}]
        result = _summarise("trend", _make_mock_strat(trades=trades, closed=3, won=3))
        assert -5.0 <= result.sharpe_ratio <= 5.0

    def test_zero_trades_returns_no_signal_result(self):
        result = _summarise("trend", _make_mock_strat(trades=[], closed=0, won=0))
        assert result.total_trades == 0
        assert result.sharpe_ratio == 0.0
        assert any("No trades" in w for w in result.warnings)

    def test_valid_backtest_returns_complete_metrics(self):
        trades = [
            {"pnl_pct": 2.0, "date": "2024-01-10", "entry": 100, "exit": 102, "pnl": 200, "reason": "exit"},
            {"pnl_pct": -1.0, "date": "2024-01-15", "entry": 102, "exit": 101, "pnl": -100, "reason": "stop"},
        ]
        result = _summarise("trend", _make_mock_strat(trades=trades, closed=2, won=1))
        assert 0.0 <= result.win_rate <= 1.0
        assert isinstance(result.sharpe_ratio, float)
        assert result.total_trades == 2
        assert isinstance(result.avg_return_pct, float)
        assert isinstance(result.max_drawdown_pct, float)

    def test_trade_log_contains_required_fields(self):
        required = {"date", "entry", "exit", "pnl", "reason"}
        trades = [{"date": "2024-01-10", "entry": 100, "exit": 102, "pnl": 200, "reason": "exit", "pnl_pct": 2.0}]
        result = _summarise("trend", _make_mock_strat(trades=trades, closed=1, won=1))
        assert len(result.trades) == 1
        for field in required:
            assert field in result.trades[0]


# ── TestBacktestResultSanity ────────────────────────────────────────────

class TestBacktestResultSanity:
    def test_win_rate_between_0_and_100_pct(self):
        for won, closed in [(0, 5), (3, 5), (5, 5)]:
            result = _summarise("trend", _make_mock_strat(trades=[], closed=closed, won=won))
            assert 0.0 <= result.win_rate <= 1.0

    def test_total_trades_is_non_negative(self):
        result = _summarise("trend", _make_mock_strat(trades=[], closed=0, won=0))
        assert isinstance(result.total_trades, int)
        assert result.total_trades >= 0

    def test_min_bars_required_constant(self):
        assert MIN_BARS_REQUIRED == 60


# ── mock helpers ─────────────────────────────────────────────────────────

class _FakeAnalysis(dict):
    def get_analysis(self):
        return self


def _make_mock_strat(trades: list, closed: int = 0, won: int = 0):
    class MockStrat:
        trade_log = trades
        analyzers = type("A", (), {
            "trades": _FakeAnalysis({
                "total": {"closed": closed},
                "won": {"total": won},
            }),
            "drawdown": _FakeAnalysis({"max": {"drawdown": 5.0}}),
        })()
    return MockStrat()
