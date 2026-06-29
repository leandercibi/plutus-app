from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# --- shared ---


class Universe(Base):
    """Point-in-time universe (A17). One row per (symbol, as_of_date)."""

    __tablename__ = "universe"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    as_of_date: Mapped[date] = mapped_column(index=True)
    median_traded_value_inr: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    free_float_mcap_inr: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 2), nullable=True
    )
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_fno_listed: Mapped[bool] = mapped_column(default=False)
    in_universe: Mapped[bool]
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date"),
        CheckConstraint("median_traded_value_inr >= 0", name="ck_universe_mtv_nonneg"),
    )


class RegimeSnapshot(Base):
    __tablename__ = "regime_snapshot"
    as_of_date: Mapped[date] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(16))
    nifty_close: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    pct_above_50dma: Mapped[float]
    pct_above_200dma: Mapped[float]
    advance_decline: Mapped[float]
    india_vix: Mapped[float]
    fii_flow_inr: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    dii_flow_inr: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    breadth_confirmed_flip: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (
        CheckConstraint("label IN ('BULL','BEAR','SIDEWAYS')", name="ck_regime_label"),
    )


class CostModelRun(Base):
    __tablename__ = "cost_model_run"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime]


class BundleStatPerRegime(Base):
    """B14. Walk-forward OOS shrunk Sharpe per (bundle, regime, as_of_date)."""

    __tablename__ = "bundle_stat_per_regime"
    id: Mapped[int] = mapped_column(primary_key=True)
    bundle: Mapped[str] = mapped_column(String(32), index=True)
    regime: Mapped[str] = mapped_column(String(16), index=True)
    as_of_date: Mapped[date] = mapped_column(index=True)
    oos_sharpe_shrunk: Mapped[float]
    oos_expectancy_R: Mapped[float]
    n_trades: Mapped[int]
    ci_low: Mapped[float]
    ci_high: Mapped[float]
    __table_args__ = (
        UniqueConstraint("bundle", "regime", "as_of_date"),
        CheckConstraint(
            "oos_sharpe_shrunk BETWEEN -3 AND 3", name="ck_bundle_stat_sharpe_range"
        ),
    )


class CalibrationRow(Base):
    """A14. SPRT/CI-aware calibration per (bucket, regime)."""

    __tablename__ = "calibration_row"
    id: Mapped[int] = mapped_column(primary_key=True)
    bucket: Mapped[str] = mapped_column(String(64), index=True)
    regime: Mapped[str] = mapped_column(String(16), index=True)
    n_closed: Mapped[int]
    win_rate: Mapped[float]
    expectancy_R: Mapped[float]
    ci_low_R: Mapped[float]
    ci_high_R: Mapped[float]
    sprt_state: Mapped[str] = mapped_column(String(16))
    last_updated: Mapped[datetime]
    confidence_band: Mapped[str] = mapped_column(String(8))
    __table_args__ = (
        CheckConstraint(
            "sprt_state IN ('accept_H0','accept_H1','continue')", name="ck_calib_sprt"
        ),
        CheckConstraint(
            '"ci_low_R" <= "expectancy_R" AND "expectancy_R" <= "ci_high_R"',
            name="ck_calib_ci_order",
        ),
        CheckConstraint(
            "confidence_band IN ('low','medium','high')", name="ck_calib_band"
        ),
    )


# --- swing ---


class SwingSignal(Base):
    __tablename__ = "swing_signal"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    bundle: Mapped[str] = mapped_column(String(32))
    score: Mapped[int]
    label: Mapped[str] = mapped_column(String(16))
    entry: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    target_1: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    target_2: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    expectancy_R: Mapped[float]
    drawn_rr: Mapped[float]
    regime_at_signal: Mapped[str] = mapped_column(String(16))
    pillar_breakdown_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    counterfactual_text: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime]
    __table_args__ = (
        CheckConstraint(
            "label IN ('BUY','BUY_WATCH','WATCH','HOLD','AVOID')",
            name="ck_swing_signal_label",
        ),
    )


class SwingTrade(Base):
    __tablename__ = "swing_trade"
    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("swing_signal.id"))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    bundle: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(16))
    opened_at: Mapped[datetime]
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    qty: Mapped[int]
    risk_R: Mapped[float]
    exit_reason: Mapped[str | None] = mapped_column(nullable=True)
    realized_R: Mapped[float | None] = mapped_column(nullable=True)
    mfe_R: Mapped[float | None] = mapped_column(nullable=True)
    mae_R: Mapped[float | None] = mapped_column(nullable=True)
    __table_args__ = (
        CheckConstraint(
            "state IN ('OPEN','T1_HIT','CLOSED_WIN','CLOSED_LOSS','SCRATCHED','EXPIRED')",
            name="ck_swing_trade_state",
        ),
        CheckConstraint(
            "state NOT IN ('CLOSED_WIN','CLOSED_LOSS') "
            'OR (closed_at IS NOT NULL AND "realized_R" IS NOT NULL)',
            name="ck_swing_trade_close_requires_fields",
        ),
    )


class Fill(Base):
    """Both mock (backtest/paper) and real (user-logged) fills."""

    __tablename__ = "fill"
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("swing_trade.id"))
    kind: Mapped[str] = mapped_column(String(8))
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[int]
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    cost_inr: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    slippage_bps: Mapped[float | None] = mapped_column(nullable=True)
    filled_at: Mapped[datetime]
    __table_args__ = (
        CheckConstraint("kind IN ('MOCK','REAL')", name="ck_fill_kind"),
        CheckConstraint("side IN ('BUY','SELL')", name="ck_fill_side"),
    )


# --- accumulation ---


class AccumulationCandidate(Base):
    __tablename__ = "accumulation_candidate"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[int]
    label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rs_30: Mapped[float]
    rs_90: Mapped[float]
    rs_180: Mapped[float]
    quality_pillar: Mapped[int | None] = mapped_column(nullable=True)
    growth_pillar: Mapped[int | None] = mapped_column(nullable=True)
    valuation_pillar: Mapped[int | None] = mapped_column(nullable=True)
    rs_pillar: Mapped[int | None] = mapped_column(nullable=True)
    cagr_eps_3y: Mapped[float | None] = mapped_column(nullable=True)
    cagr_eps_5y: Mapped[float | None] = mapped_column(nullable=True)
    valuation_pillar_pct: Mapped[float]
    thesis_text: Mapped[str]
    hard_avoid_active: Mapped[bool] = mapped_column(default=False)
    hard_avoid_reasons_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime]


class AccumulationPosition(Base):
    __tablename__ = "accumulation_position"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(24))
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    qty_total: Mapped[int]
    opened_at: Mapped[datetime]
    last_thesis_check_at: Mapped[datetime]
    paused_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    __table_args__ = (
        CheckConstraint("qty_total >= 0", name="ck_accum_qty_nonneg"),
        CheckConstraint(
            "state IN ('BUILDING','FULL','PAUSED','EXITED','CONVERTED_TO_SWING')",
            name="ck_accum_state",
        ),
    )


class Tranche(Base):
    __tablename__ = "tranche"
    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("accumulation_position.id"))
    seq: Mapped[int]
    qty: Mapped[int | None] = mapped_column(nullable=True)
    atr_normalized_trigger_pct: Mapped[float]
    filled_at_price: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    filled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    thesis_revalidated: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (CheckConstraint("seq BETWEEN 1 AND 5", name="ck_tranche_seq"),)


# --- reports ---


class WeeklyPostmortem(Base):
    __tablename__ = "weekly_postmortem"
    week_ending: Mapped[date] = mapped_column(primary_key=True)
    swing_return_pct: Mapped[float]
    nifty_return_pct: Mapped[float]
    regime_switched_return_pct: Mapped[float]
    random_baseline_return_pct: Mapped[float]
    n_swing_trades_closed: Mapped[int]
    drawdown_pct: Mapped[float]
    report_md_path: Mapped[str]


class AlertCooldown(Base):
    """A16. Per-stock cooldown rows, separate keys for SL vs warning."""

    __tablename__ = "alert_cooldown"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    last_fired_at: Mapped[datetime]
    __table_args__ = (
        CheckConstraint(
            "kind IN ('SL_BREACH','SL_WARNING','T1_HIT','NO_PROGRESS')",
            name="ck_cooldown_kind",
        ),
    )


class Notification(Base):
    __tablename__ = "notification"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(String(512))
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dismissed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime]
    __table_args__ = (
        CheckConstraint(
            "kind IN ('SL_PROXIMITY','PNL_UPDATE','T1_PROXIMITY','PRICE_ALERT','SL_BREACH')",
            name="ck_notification_kind",
        ),
        CheckConstraint(
            "severity IN ('INFO','WARNING','URGENT')",
            name="ck_notification_severity",
        ),
    )


class LatestPrice(Base):
    __tablename__ = "latest_price"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    source: Mapped[str] = mapped_column(String(16))
    fetched_at: Mapped[datetime]


class DrawdownGovernorState(Base):
    """B4. Single-row upserted state for the 3-day recovery rule."""

    __tablename__ = "drawdown_governor_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    as_of_date: Mapped[date] = mapped_column(unique=True, index=True)
    pool_value: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    high_water_mark: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    multiplier: Mapped[float]
    consecutive_recovery_days: Mapped[int] = mapped_column(default=0)


class RunLogRow(Base):
    """Scheduler job run history (spec 13 §8)."""

    __tablename__ = "run_log"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_name: Mapped[str] = mapped_column(String(48), index=True)
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str | None] = mapped_column(String(8), nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class WalkForwardRun(Base):
    """4B. IS/OOS walk-forward results per (symbol, bundle) run."""

    __tablename__ = "walk_forward_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    bundle: Mapped[str] = mapped_column(String(32))
    window_days: Mapped[int]
    step_days: Mapped[int]
    is_sharpe_median: Mapped[float]
    oos_sharpe_median: Mapped[float]
    overfit_flag: Mapped[bool]
    windows_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime]
