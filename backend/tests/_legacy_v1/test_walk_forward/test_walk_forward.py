# tests/test_walk_forward/test_walk_forward.py
"""
Tests for walk_forward.py — 100% offline.

Strategy:
  - Use synthetic DataFrames from test_bundle_hardening/conftest.py (no network).
  - Test window slicing logic, overfit detection, summary aggregation.
  - DB persistence uses an in-memory SQLite session.
"""
from __future__ import annotations

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "-1")

import pytest

from tests.test_bundle_hardening.conftest import (
    make_bull_df,
    make_sideways_df,
    make_volatile_df,
)

from plutus.backtesting.walk_forward import (
    OVERFIT_THRESHOLD,
    WindowResult,
    WalkForwardSummary,
    _overfit,
    _run_on_slice,
    run_walk_forward,
)


# ── _overfit logic ─────────────────────────────────────────────────────────────


class TestOverfitLogic:
    def test_no_overfit_when_oos_close_to_is(self):
        # OOS Sharpe = 80% of IS → drop of 20% < 50% threshold
        assert not _overfit(is_sharpe=1.0, oos_sharpe=0.8)

    def test_overfit_when_oos_drops_more_than_50pct(self):
        # OOS = 40% of IS → drop of 60% > 50% threshold
        assert _overfit(is_sharpe=1.0, oos_sharpe=0.4)

    def test_no_overfit_when_is_sharpe_is_zero(self):
        # IS = 0 → overfit check skipped (division by zero guard)
        assert not _overfit(is_sharpe=0.0, oos_sharpe=-1.0)

    def test_no_overfit_when_is_sharpe_is_negative(self):
        # IS negative → overfit check skipped
        assert not _overfit(is_sharpe=-0.5, oos_sharpe=-2.0)

    def test_overfit_just_below_threshold(self):
        # OOS = 49% of IS → strict < 50% threshold → overfit
        assert _overfit(is_sharpe=1.0, oos_sharpe=0.49)

    def test_oos_better_than_is_not_overfit(self):
        assert not _overfit(is_sharpe=1.0, oos_sharpe=1.5)


# ── _run_on_slice ──────────────────────────────────────────────────────────────


class TestRunOnSlice:
    def test_returns_bundle_result(self):
        df = make_bull_df(n=200)
        result = _run_on_slice(df.iloc[:150], "trend")
        assert result.bundle_name == "trend"
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.total_trades, int)

    def test_reversal_on_sideways(self):
        df = make_sideways_df(n=200)
        result = _run_on_slice(df.iloc[:150], "reversal")
        assert result.bundle_name == "reversal"

    def test_smc_on_volatile(self):
        df = make_volatile_df(n=200)
        result = _run_on_slice(df.iloc[:150], "smc")
        assert result.bundle_name == "smc"


# ── run_walk_forward with pre-fetched df ──────────────────────────────────────


class TestRunWalkForward:
    def test_basic_window_slicing(self):
        df = make_bull_df(n=300)
        summary = run_walk_forward(
            "TESTSTOCK",
            "trend",
            window_bars=80,
            step_bars=20,
            oos_bars=70,
            df=df,
        )
        assert len(summary.windows) >= 2, "Should produce at least 2 windows"
        assert summary.symbol == "TESTSTOCK"
        assert summary.bundle_name == "trend"

    def test_window_dates_dont_overlap(self):
        df = make_bull_df(n=300)
        summary = run_walk_forward(
            "TESTSTOCK",
            "trend",
            window_bars=80,
            step_bars=20,
            oos_bars=70,
            df=df,
        )
        for i in range(1, len(summary.windows)):
            prev = summary.windows[i - 1]
            curr = summary.windows[i]
            # Each window's IS start should advance by step
            assert curr.is_start >= prev.is_start, "Windows not advancing"
            # OOS must come after IS
            assert curr.oos_start > curr.is_end

    def test_window_is_oos_boundary(self):
        df = make_bull_df(n=300)
        summary = run_walk_forward(
            "TESTSTOCK",
            "trend",
            window_bars=80,
            step_bars=20,
            oos_bars=70,
            df=df,
        )
        for w in summary.windows:
            # IS end must be before OOS start
            assert w.is_end < w.oos_start
            assert w.oos_end >= w.oos_start

    def test_too_small_df_returns_no_data(self):
        df = make_bull_df(n=50)
        summary = run_walk_forward(
            "TESTSTOCK",
            "trend",
            window_bars=60,
            step_bars=7,
            oos_bars=30,
            df=df,
        )
        assert summary.verdict == "NO_DATA"
        assert len(summary.windows) == 0

    def test_invalid_bundle_raises(self):
        df = make_bull_df(n=200)
        with pytest.raises(ValueError, match="Unknown bundle"):
            run_walk_forward("TESTSTOCK", "nonexistent", df=df)

    def test_sharpe_values_present(self):
        df = make_bull_df(n=300)
        summary = run_walk_forward(
            "TESTSTOCK",
            "trend",
            window_bars=80,
            step_bars=20,
            oos_bars=70,
            df=df,
        )
        for w in summary.windows:
            assert isinstance(w.is_sharpe, float)
            assert isinstance(w.oos_sharpe, float)

    def test_trade_counts_non_negative(self):
        df = make_bull_df(n=300)
        summary = run_walk_forward(
            "TESTSTOCK",
            "trend",
            window_bars=80,
            step_bars=20,
            oos_bars=70,
            df=df,
        )
        for w in summary.windows:
            assert w.is_trades >= 0
            assert w.oos_trades >= 0


# ── Summary aggregation ────────────────────────────────────────────────────────


class TestSummaryAggregation:
    def test_mean_sharpe_computed(self):
        df = make_bull_df(n=300)
        summary = run_walk_forward(
            "TESTSTOCK",
            "trend",
            window_bars=80,
            step_bars=20,
            oos_bars=70,
            df=df,
        )
        if summary.windows:
            expected_is = sum(w.is_sharpe for w in summary.windows) / len(
                summary.windows
            )
            assert abs(summary.mean_is_sharpe - expected_is) < 1e-2

    def test_overfit_count_matches_windows(self):
        df = make_bull_df(n=300)
        summary = run_walk_forward(
            "TESTSTOCK",
            "trend",
            window_bars=80,
            step_bars=20,
            oos_bars=70,
            df=df,
        )
        actual_overfit_count = sum(1 for w in summary.windows if w.overfit_flag)
        assert summary.overfit_window_count == actual_overfit_count

    def test_overfit_pct_consistent(self):
        df = make_bull_df(n=300)
        summary = run_walk_forward(
            "TESTSTOCK",
            "trend",
            window_bars=80,
            step_bars=20,
            oos_bars=70,
            df=df,
        )
        if summary.windows:
            expected_pct = summary.overfit_window_count / len(summary.windows) * 100
            assert abs(summary.overfit_pct - expected_pct) < 0.1

    def test_verdict_is_one_of_valid_values(self):
        df = make_bull_df(n=300)
        summary = run_walk_forward(
            "TESTSTOCK",
            "trend",
            window_bars=80,
            step_bars=20,
            oos_bars=70,
            df=df,
        )
        assert summary.verdict in ("ROBUST", "SUSPECT", "OVERFIT", "NO_DATA")


# ── DB persistence ─────────────────────────────────────────────────────────────


class TestPersistence:
    def test_persist_creates_rows(self, tmp_path, monkeypatch):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from plutus.db.session import Base
        from plutus.db.models import WalkForwardRun

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)

        df = make_bull_df(n=300)
        summary = run_walk_forward(
            "RELIANCE",
            "trend",
            window_bars=80,
            step_bars=20,
            oos_bars=40,
            df=df,
        )

        from plutus.backtesting.walk_forward import persist_walk_forward

        with Session() as session:
            persist_walk_forward(summary, db_session=session)
            count = session.query(WalkForwardRun).count()

        assert count == len(summary.windows)

    def test_persist_stores_correct_symbol(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from plutus.db.session import Base
        from plutus.db.models import WalkForwardRun
        from plutus.backtesting.walk_forward import persist_walk_forward

        engine = create_engine(f"sqlite:///{tmp_path}/test2.db")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)

        df = make_bull_df(n=300)
        summary = run_walk_forward(
            "HDFCBANK",
            "trend",
            window_bars=80,
            step_bars=20,
            oos_bars=40,
            df=df,
        )

        with Session() as session:
            persist_walk_forward(summary, db_session=session)
            rows = session.query(WalkForwardRun).all()

        for row in rows:
            assert row.symbol == "HDFCBANK"
            assert row.bundle_name == "trend"
