# tests/test_bundle_hardening/test_vcp_pead.py
"""
Phase 5 acceptance tests for VCPBundle and PEADBundle.

Contract per bundle:
  1. Generates ≥ 1 trade on engineered fixture data.
  2. BEAR regime gate suppresses all signals.
  3. Volume gate kills signals when raised to 100×.
  4. ATR discipline: no single trade loses > 25%.
  5. ATR stop/target params match base-class defaults.
  6. VCP: sector_rs_rank gate and n_contractions param behave correctly.
  7. PEAD: earnings_months_only gate; hold_days_max triggers time exit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.test_bundle_hardening.conftest import (
    run_strategy, make_vcp_df, make_pead_df, _dates,
)
from plutus.strategies.bundle_vcp import VCPBundle
from plutus.strategies.bundle_pead import PEADBundle
from plutus.backtesting.runner import BUNDLE_MAP


def _run(cls, df, **kw):
    return run_strategy(df, cls, **kw)


def _assert_trade_sanity(strat, label: str):
    for t in strat.trade_log:
        assert t["entry"] > 0, f"{label}: zero entry price"
        assert t["pnl_pct"] > -25, f"{label}: loss exceeded ATR discipline: {t}"


# =========================================================================== #
# VCPBundle
# =========================================================================== #

class TestVCPBundle:
    def test_generates_trades_in_bull(self, vcp_df):
        strat = _run(VCPBundle, vcp_df)
        assert len(strat.trade_log) >= 1, "VCPBundle: no trades on engineered VCP data"

    def test_bear_regime_suppresses_signals(self, vcp_df):
        strat = _run(VCPBundle, vcp_df, nifty_trend="BEAR")
        assert len(strat.trade_log) == 0

    def test_vol_gate_kills_signals(self, vcp_df):
        strat = _run(VCPBundle, vcp_df, vol_breakout_ratio=100.0)
        assert len(strat.trade_log) == 0

    def test_sector_rank_gate_fails_bottom(self, vcp_df):
        # Rank = 10 but top_n = 3 → gate should block
        strat = _run(VCPBundle, vcp_df, sector_rs_rank=10, sector_rs_top_n=3)
        assert len(strat.trade_log) == 0

    def test_sector_rank_gate_passes_top(self, vcp_df):
        # Rank = 1 is in top 5 → signals allowed
        strat = _run(VCPBundle, vcp_df, sector_rs_rank=1, sector_rs_top_n=5)
        assert len(strat.trade_log) >= 1

    def test_fewer_contractions_still_signals(self, vcp_df):
        # With n_contractions=2 the bar still qualifies (pattern only needs 2 stages)
        strat = _run(VCPBundle, vcp_df, n_contractions=2)
        assert len(strat.trade_log) >= 1

    def test_excessive_contractions_kills_signals(self, vcp_df):
        # Requiring 8 contractions on 5-bar windows needs 9×5=45 bars of setup —
        # our fixture only has 20 setup bars, so the check should fail
        strat = _run(VCPBundle, vcp_df, n_contractions=8)
        assert len(strat.trade_log) == 0

    def test_trade_sanity(self, vcp_df):
        _assert_trade_sanity(_run(VCPBundle, vcp_df), "VCPBundle")

    def test_atr_defaults(self, vcp_df):
        strat = _run(VCPBundle, vcp_df)
        assert strat.p.atr_stop_mult == 1.5
        assert strat.p.min_rr == 2.0

    def test_rr_floor_enforced(self, vcp_df):
        # Lower T2 mult so R:R < 2.0 — entry must be skipped
        strat = _run(VCPBundle, vcp_df, atr_t2_mult=1.0)
        assert len(strat.trade_log) == 0

    def test_bundle_registered_in_bundle_map(self):
        assert "vcp" in BUNDLE_MAP
        assert BUNDLE_MAP["vcp"] is VCPBundle


# =========================================================================== #
# PEADBundle
# =========================================================================== #

class TestPEADBundle:
    def test_generates_trades(self, pead_df):
        strat = _run(PEADBundle, pead_df, earnings_months_only=False)
        assert len(strat.trade_log) >= 1, "PEADBundle: no trades on engineered PEAD data"

    def test_bear_regime_suppresses_signals(self, pead_df):
        strat = _run(PEADBundle, pead_df, earnings_months_only=False, nifty_trend="BEAR")
        assert len(strat.trade_log) == 0

    def test_vol_gate_kills_signals(self, pead_df):
        strat = _run(PEADBundle, pead_df, earnings_months_only=False, vol_min_ratio=100.0)
        assert len(strat.trade_log) == 0

    def test_gap_threshold_too_high_kills_signals(self, pead_df):
        # Fixture has a 7% gap — raising threshold above that should block entry
        strat = _run(PEADBundle, pead_df, earnings_months_only=False, gap_min_pct=20.0)
        assert len(strat.trade_log) == 0

    def test_earnings_months_only_blocks_non_earnings_months(self, pead_df):
        # The fixture's gap bar falls outside Jan/Apr/Jul/Oct (dates end ~today)
        # so earnings_months_only=True should produce 0 trades.
        # NOTE: this test is only meaningful when today is not Jan/Apr/Jul/Oct.
        import datetime
        gap_bar_date = pead_df.index[130]
        if gap_bar_date.month in (1, 4, 7, 10):
            pytest.skip("gap bar coincidentally falls in an earnings month")
        strat = _run(PEADBundle, pead_df, earnings_months_only=True)
        assert len(strat.trade_log) == 0

    def test_earnings_months_only_off_allows_signals(self, pead_df):
        strat = _run(PEADBundle, pead_df, earnings_months_only=False)
        assert len(strat.trade_log) >= 1

    def test_pullback_window_too_tight_kills_signals(self, pead_df):
        # The entry fires on bar 2 after the gap; pullback_window=1 misses it
        strat = _run(PEADBundle, pead_df, earnings_months_only=False, pullback_window=1)
        assert len(strat.trade_log) == 0

    def test_hold_days_max_forces_exit(self, pead_df):
        # hold_days_max=1 forces exit the very next bar — trade must still be logged
        strat = _run(PEADBundle, pead_df, earnings_months_only=False, hold_days_max=1)
        assert len(strat.trade_log) >= 1
        for t in strat.trade_log:
            assert t["bars_held"] <= 2  # 1 (or sometimes 2 due to order latency)

    def test_trade_sanity(self, pead_df):
        _assert_trade_sanity(
            _run(PEADBundle, pead_df, earnings_months_only=False), "PEADBundle"
        )

    def test_atr_defaults(self, pead_df):
        strat = _run(PEADBundle, pead_df, earnings_months_only=False)
        assert strat.p.atr_stop_mult == 1.5
        assert strat.p.min_rr == 2.0

    def test_rr_floor_enforced(self, pead_df):
        # Lower T2 mult so R:R < 2.0 — no entries should occur
        strat = _run(PEADBundle, pead_df, earnings_months_only=False, atr_t2_mult=1.0)
        assert len(strat.trade_log) == 0

    def test_bundle_registered_in_bundle_map(self):
        assert "pead" in BUNDLE_MAP
        assert BUNDLE_MAP["pead"] is PEADBundle


# =========================================================================== #
# Cross-bundle: all 7 bundles in BUNDLE_MAP are importable and runnable
# =========================================================================== #

class TestBundleMapCompleteness:
    def test_all_expected_bundles_registered(self):
        expected = {"trend", "reversal", "breakout", "smc", "composite", "vcp", "pead"}
        assert expected.issubset(BUNDLE_MAP.keys())

    def test_vcp_runs_without_crash_on_bull(self):
        df = make_vcp_df()
        strat = _run(BUNDLE_MAP["vcp"], df)
        assert strat is not None

    def test_pead_runs_without_crash_on_pead_data(self):
        df = make_pead_df()
        strat = _run(BUNDLE_MAP["pead"], df, earnings_months_only=False)
        assert strat is not None
