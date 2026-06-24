from __future__ import annotations

from decimal import Decimal

from plutus.dashboard.data import (
    CalibrationLineView,
    CalibrationView,
    CandidateView,
    HomeRow,
    HomeView,
    LabBundleStatView,
    PillarBreakdownView,
    PositionView,
    PostmortemBundleRow,
    PostmortemView,
    RunLogRowView,
    SettingsFieldView,
    SettingsView,
    SignalView,
    StrategyLabView,
    TrancheView,
    TunerProposalView,
    UserFlowView,
)
from plutus.shared.benchmarks.strip import BenchmarkResult
from plutus.shared.regime.detector import RegimeVerdict
from plutus.shared.risk.cash_position import CashDecision


def benchmark_fixture() -> BenchmarkResult:
    return BenchmarkResult(
        plutus_net_pct=3.2,
        nifty_net_pct=1.1,
        regime_switched_net_pct=0.8,
        random_liquid_net_pct=-0.4,
        plutus_profit_factor=1.8,
        plutus_n_trades=12,
    )


def home_view(with_cash: bool = True) -> HomeView:
    cash = (
        CashDecision(
            deploy_count=1,
            cash_pct_of_pool=0.6,
            reason="market offered 1 qualifying setup; 60% of swing pool held in cash.",
        )
        if with_cash
        else None
    )
    return HomeView(
        total_capital=Decimal("1000000"),
        swing_allocated=Decimal("300000"),
        accumulation_allocated=Decimal("100000"),
        cash_reserve=Decimal("600000"),
        regime=RegimeVerdict(label="BEAR", confidence="high", reasons=["vix elevated"]),
        cash_decision=cash,
        swing_mode="Active",
        accumulation_mode="Active",
        swing_rows=[
            HomeRow("INFY", 76, "BUY", 0.76, "E +0.18R · n=42 · med"),
            HomeRow("TCS", 70, "WATCH", 0.70, "E +0.05R · n=20 · low"),
            HomeRow("WIPRO", 64, "WATCH", 0.64, "E -0.02R · n=15 · low"),
        ],
        accumulation_rows=[
            HomeRow("HDFCBANK", 80, "BUILDING", 0.80, "RS 30/90/180: 68/72/74 · intact", [1, 2]),
            HomeRow("ITC", 72, "BUILDING", 0.72, "RS 30/90/180: 60/64/66 · intact", [1]),
            HomeRow("RELIANCE", 78, "BUILDING", 0.78, "RS 30/90/180: 70/72/75 · intact", [1, 2, 3]),
        ],
    )


def signal_view(score: int = 70) -> SignalView:
    return SignalView(
        id=1,
        symbol="INFY",
        bundle="trend",
        score=score,
        label="BUY_WATCH",
        entry=Decimal("1500.50"),
        stop_loss=Decimal("1440.00"),
        target_1=Decimal("1620.00"),
        target_2=Decimal("1700.00"),
        pillars=PillarBreakdownView(
            technical=24, expectancy=20, flow=11, sentiment=4, regime_fit=12, fundamentals=7
        ),
        calibration_n=84,
        calibration_band="high",
        counterfactual="upgrades to BUY if entry < ₹1480 or delivery > 50%",
        delivery_pct=44.5,
        adv_use_pct=8.0,
        circuit_hits_90d=0,
        earnings_in_window=False,
        sector_heat=2.1,
        regime="BULL",
    )


def position_views() -> list[PositionView]:
    return [
        PositionView(
            trade_id=1,
            symbol="INFY",
            bundle="trend",
            age_days=4,
            risk_R=1.0,
            realized_R=0.6,
            mfe_R=1.1,
            elapsed_to_t1_pct=40.0,
            trailing_stop=None,
            is_open=True,
        ),
        PositionView(
            trade_id=2,
            symbol="TCS",
            bundle="breakout",
            age_days=10,
            risk_R=1.0,
            realized_R=1.8,
            mfe_R=2.0,
            elapsed_to_t1_pct=100.0,
            trailing_stop=Decimal("3550.00"),
            is_open=False,
            exit_reason="T1 hit",
            slippage_delta_bps=6.2,
        ),
    ]


def candidate_views() -> list[CandidateView]:
    return [
        CandidateView(
            symbol="HDFCBANK",
            label="ACCUMULATE_NOW",
            quality=26,
            growth=20,
            valuation=28,
            rs_blend=12,
            rs_30=68.0,
            rs_90=72.0,
            rs_180=74.0,
            cagr_eps_3y=14.0,
            cagr_eps_5y=12.0,
            valuation_capped=True,
        ),
        CandidateView(
            symbol="YESBANK",
            label="AVOID",
            quality=8,
            growth=5,
            valuation=10,
            rs_blend=3,
            rs_30=20.0,
            rs_90=18.0,
            rs_180=15.0,
            cagr_eps_3y=-30.0,
            cagr_eps_5y=-25.0,
            valuation_capped=False,
            hard_avoid_reasons=["D/E breach", "EPS collapse > 50% YoY"],
        ),
    ]


def tranche_views() -> list[TrancheView]:
    return [
        TrancheView(
            position_id=1,
            symbol="HDFCBANK",
            seqs_filled=[1, 2],
            total_tranches=5,
            avg_cost=Decimal("1620.00"),
            pct_gain_loss=3.4,
            last_thesis_check="2025-01-04",
            last_thesis_result="intact",
            paused=False,
        ),
        TrancheView(
            position_id=2,
            symbol="ITC",
            seqs_filled=[1],
            total_tranches=5,
            avg_cost=Decimal("440.00"),
            pct_gain_loss=-1.2,
            last_thesis_check="2025-01-04",
            last_thesis_result="quality dropped 12 pts",
            paused=True,
            paused_reason="quality pillar dropped > 10 points",
        ),
    ]


def postmortem_view() -> PostmortemView:
    return PostmortemView(
        week_ending="2025-01-05",
        available_weeks=["2025-01-05", "2024-12-29"],
        benchmarks=benchmark_fixture(),
        bundle_rows=[
            PostmortemBundleRow("trend", 8, 0.62, 0.2, 0.7, 0.45),
            PostmortemBundleRow("breakout", 4, 0.50, -0.1, 0.6, 0.25),
        ],
        wrong_direction_count=2,
        no_progress_count=1,
        slippage_divergence_bps=7.5,
    )


def calibration_view(auto_tune: bool) -> CalibrationView:
    return CalibrationView(
        lines=[
            CalibrationLineView(
                bucket="trend_70_75",
                regime="BULL",
                n_closed=42,
                win_rate=0.6,
                expectancy_R=0.45,
                ci_low_R=0.2,
                ci_high_R=0.7,
                confidence_band="medium",
                sprt_state="continue",
            ),
        ],
        proposals=[
            TunerProposalView(
                bundle="trend",
                regime="BULL",
                parameter="target_atr_mult",
                old_value=2.0,
                proposed_value=2.5,
                delta_expectancy_R=0.12,
                family_corrected_p=0.02,
            ),
        ],
        auto_tune_enabled=auto_tune,
    )


def user_flow_view(fresh: bool) -> UserFlowView:
    return UserFlowView(
        run_log=[
            RunLogRowView("sunday_full_run", "2025-01-05 19:00", "2025-01-05 19:30", "OK"),
            RunLogRowView("monday_revalidation", "2025-01-06 09:10", None, None),
        ],
        freshness_ok=fresh,
        freshness_detail="latest candle 2025-01-05" if fresh else "stale: candle 2024-12-31",
    )


def settings_view() -> SettingsView:
    return SettingsView(
        fields=[
            SettingsFieldView("risk_per_trade_pct", "0.01", editable=True),
            SettingsFieldView("max_concurrent_swing_positions", "10", editable=True),
            SettingsFieldView("midweek_mini_screen_enabled", "False", editable=True),
            SettingsFieldView("db_url", "sqlite:///./plutus.db", editable=False),
        ]
    )


def strategy_lab_view() -> StrategyLabView:
    return StrategyLabView(
        available_bundles=["trend", "breakout", "vcp", "composite", "smc"],
        available_symbols=["INFY", "TCS"],
        smc_display_only=True,
        last_run_stats=[LabBundleStatView("trend", 1.2, 0.4, 50)],
        last_run_benchmarks=benchmark_fixture(),
    )
