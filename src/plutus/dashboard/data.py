from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from plutus.shared.benchmarks.strip import BenchmarkResult
from plutus.shared.regime.detector import RegimeVerdict
from plutus.shared.risk.cash_position import CashDecision

SwingLabel = Literal["BUY", "BUY_WATCH", "WATCH", "HOLD", "AVOID"]
AccumulationLabel = Literal["ACCUMULATE_NOW", "BUILD_SLOWLY", "WATCH", "AVOID"]
Band = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class PillarBreakdownView:
    technical: int
    expectancy: int
    flow: int
    sentiment: int
    regime_fit: int
    fundamentals: int


@dataclass(frozen=True)
class SignalView:
    id: int
    symbol: str
    bundle: str
    score: int
    label: SwingLabel
    entry: Decimal
    stop_loss: Decimal
    target_1: Decimal
    target_2: Decimal
    pillars: PillarBreakdownView
    calibration_n: int
    calibration_band: Band
    counterfactual: str
    delivery_pct: float
    adv_use_pct: float
    circuit_hits_90d: int
    earnings_in_window: bool
    sector_heat: float
    regime: str


@dataclass(frozen=True)
class HomeRow:
    symbol: str
    score: int
    status: str
    bar_pct: float
    detail: str
    tranches_filled: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class HomeView:
    total_capital: Decimal
    swing_allocated: Decimal
    accumulation_allocated: Decimal
    cash_reserve: Decimal
    regime: RegimeVerdict
    cash_decision: CashDecision | None
    swing_mode: Literal["Active", "Paused"]
    accumulation_mode: Literal["Active", "Paused"]
    swing_rows: list[HomeRow]
    accumulation_rows: list[HomeRow]


@dataclass(frozen=True)
class PositionView:
    trade_id: int
    symbol: str
    bundle: str
    age_days: int
    risk_R: float
    realized_R: float
    mfe_R: float
    elapsed_to_t1_pct: float
    trailing_stop: Decimal | None
    is_open: bool
    exit_reason: str | None = None
    slippage_delta_bps: float | None = None


@dataclass(frozen=True)
class CandidateView:
    symbol: str
    label: AccumulationLabel
    quality: int
    growth: int
    valuation: int
    rs_blend: int
    rs_30: float
    rs_90: float
    rs_180: float
    cagr_eps_3y: float
    cagr_eps_5y: float
    valuation_capped: bool
    hard_avoid_reasons: list[str] = field(default_factory=list)
    # populated if an active AccumulationPosition exists for this symbol
    position_id: int | None = None
    tranches_filled: int = 0
    total_tranches: int = 5


@dataclass(frozen=True)
class TrancheView:
    position_id: int
    symbol: str
    seqs_filled: list[int]
    total_tranches: int
    avg_cost: Decimal
    pct_gain_loss: float
    last_thesis_check: str
    last_thesis_result: str
    paused: bool
    paused_reason: str | None = None


@dataclass(frozen=True)
class CalibrationLineView:
    bucket: str
    regime: str
    n_closed: int
    win_rate: float
    expectancy_R: float
    ci_low_R: float
    ci_high_R: float
    confidence_band: Band
    sprt_state: str


@dataclass(frozen=True)
class TunerProposalView:
    bundle: str
    regime: str
    parameter: str
    old_value: float
    proposed_value: float
    delta_expectancy_R: float
    family_corrected_p: float


@dataclass(frozen=True)
class CalibrationView:
    lines: list[CalibrationLineView]
    proposals: list[TunerProposalView]
    auto_tune_enabled: bool


@dataclass(frozen=True)
class PostmortemBundleRow:
    bundle: str
    n_trades: int
    win_rate: float
    ci_low_R: float
    ci_high_R: float
    expectancy_R: float


@dataclass(frozen=True)
class PostmortemView:
    week_ending: str
    available_weeks: list[str]
    benchmarks: BenchmarkResult
    bundle_rows: list[PostmortemBundleRow]
    wrong_direction_count: int
    no_progress_count: int
    slippage_divergence_bps: float | None


@dataclass(frozen=True)
class RunLogRowView:
    job_name: str
    started_at: str
    ended_at: str | None
    status: str | None


@dataclass(frozen=True)
class UserFlowView:
    run_log: list[RunLogRowView]
    freshness_ok: bool
    freshness_detail: str


@dataclass(frozen=True)
class SettingsFieldView:
    name: str
    value: str
    editable: bool


@dataclass(frozen=True)
class SettingsView:
    fields: list[SettingsFieldView]


@dataclass(frozen=True)
class LabBundleStatView:
    bundle: str
    oos_sharpe_shrunk: float
    expectancy_R: float
    n_trades: int


@dataclass(frozen=True)
class StrategyLabView:
    available_bundles: list[str]
    available_symbols: list[str]
    smc_display_only: bool
    last_run_stats: list[LabBundleStatView] = field(default_factory=list)
    last_run_benchmarks: BenchmarkResult | None = None
