import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Numeric,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Enum as SAEnum,
    Date,
    Index,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from plutus.db.session import Base


class RecommendationVerdict(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WATCH = "WATCH"
    AVOID = "AVOID"


class TradeDirection(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class TradeExitReason(str, enum.Enum):
    TARGET1 = "TARGET1"
    TARGET2 = "TARGET2"
    STOP = "STOP"
    MANUAL = "MANUAL"
    SIGNAL = "SIGNAL"
    EXPIRED = "EXPIRED"


class OutcomeVerdict(str, enum.Enum):
    HIT_T1 = "HIT_T1"
    HIT_T2 = "HIT_T2"
    STOPPED = "STOPPED"
    WRONG_DIRECTION = "WRONG_DIRECTION"  # STOPPED within 3 trading days of signal
    EXPIRED = "EXPIRED"
    PENDING = "PENDING"


class WeeklyRun(Base):
    __tablename__ = "weekly_runs"

    id = Column(Integer, primary_key=True)
    run_date = Column(Date, nullable=False)
    run_type = Column(
        String(20), nullable=False, default="scheduled"
    )  # 'scheduled' | 'manual'
    generated_at = Column(DateTime, nullable=True)
    market_regime = Column(String(50))  # 'BULLISH' / 'BEARISH' / 'SIDEWAYS'
    nifty_trend = Column(String(50))  # 'ABOVE_EMA50' / 'BELOW_EMA50'
    strategy_selected = Column(String(200))  # JSON string of bundle names + weights
    stocks_screened = Column(Integer)
    stocks_analysed = Column(Integer)
    total_buy_signals = Column(Integer, default=0)
    total_watch_signals = Column(Integer, default=0)
    report_md_path = Column(String(500))
    params_version_id = Column(
        String(16), nullable=True
    )  # hash of trading_params at run time
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    recommendations = relationship("Recommendation", back_populates="weekly_run")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True)
    weekly_run_id = Column(
        Integer, ForeignKey("weekly_runs.id"), nullable=True
    )  # NULL for on-demand
    symbol = Column(String(20), nullable=False, index=True)
    exchange = Column(String(10), default="NSE")
    recommendation = Column(SAEnum(RecommendationVerdict), nullable=False)
    confidence = Column(Float)  # 0–10
    entry_low = Column(Float)
    entry_high = Column(Float)
    entry_mid = Column(Numeric(12, 2))  # (entry_low + entry_high) / 2; assumed fill
    target1 = Column(Float)
    target2 = Column(Float)
    stop_loss = Column(Float)
    rr_ratio = Column(Float)
    hold_days = Column(Integer)  # backward-compat alias = hold_days_max
    hold_days_min = Column(Integer)  # e.g. 5  (from "5-8 days")
    hold_days_max = Column(Integer)  # e.g. 8  (from "5-8 days")
    strategy_used = Column(String(200))
    technical_score = Column(Float)
    sentiment_score = Column(Float)
    smart_money_score = Column(Float)
    regime_score = Column(Float, nullable=True)
    rr_score = Column(Float, nullable=True)
    reasoning_text = Column(Text)
    is_on_demand = Column(Boolean, default=False)  # True if triggered via /stock or API
    outcome = Column(SAEnum(OutcomeVerdict), default=OutcomeVerdict.PENDING, index=True)
    outcome_pct = Column(Float, nullable=True)
    outcome_fill_price = Column(Numeric(12, 2), nullable=True)
    outcome_exit_price = Column(Numeric(12, 2), nullable=True)
    outcome_exit_date = Column(Date, nullable=True)
    outcome_tracked_at = Column(DateTime, nullable=True)
    mfe_pct = Column(Float, nullable=True)  # max favorable excursion % from fill
    mae_pct = Column(Float, nullable=True)  # max adverse excursion % from fill
    revalidation_note = Column(
        String(200), nullable=True
    )  # set by Monday revalidation job
    revalidated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    weekly_run = relationship("WeeklyRun", back_populates="recommendations")
    paper_trades = relationship("PaperTrade", back_populates="recommendation")


class MockPortfolio(Base):
    __tablename__ = "mock_portfolios"

    id = Column(Integer, primary_key=True)
    name = Column(
        String(100), nullable=False, unique=True
    )  # e.g. 'aggressive_momentum'
    initial_capital = Column(Float, nullable=False)  # e.g. 100000.0
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    trades = relationship("PaperTrade", back_populates="portfolio")

    @property
    def current_cash(self) -> float:
        """Computed cash: initial_capital minus open positions plus closed trade P&L."""
        open_capital = sum(
            float(t.capital_used or 0)
            for t in self.trades
            if t.status == TradeStatus.OPEN
        )
        closed_pnl = sum(
            float(t.realised_pnl or 0)
            for t in self.trades
            if t.status == TradeStatus.CLOSED
        )
        return self.initial_capital - open_capital + closed_pnl

    @property
    def total_realised_pnl(self):
        return sum(
            t.realised_pnl or 0 for t in self.trades if t.status == TradeStatus.CLOSED
        )

    @property
    def win_rate(self):
        closed = [t for t in self.trades if t.status == TradeStatus.CLOSED]
        if not closed:
            return 0.0
        wins = [t for t in closed if (t.realised_pnl or 0) > 0]
        return len(wins) / len(closed) * 100


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(
        Integer, ForeignKey("mock_portfolios.id"), nullable=False, index=True
    )
    linked_recommendation_id = Column(
        Integer, ForeignKey("recommendations.id"), nullable=True
    )
    symbol = Column(String(20), nullable=False)
    direction = Column(SAEnum(TradeDirection), default=TradeDirection.LONG)
    entry_price = Column(Float, nullable=False)
    entry_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    shares = Column(Integer, nullable=False)
    capital_used = Column(Float, nullable=False)  # entry_price * shares
    exit_price = Column(Float, nullable=True)
    exit_date = Column(DateTime, nullable=True)
    realised_pnl = Column(Float, nullable=True)  # (exit - entry) * shares
    realised_pnl_pct = Column(Float, nullable=True)  # pnl / capital_used * 100
    strategy_used = Column(String(200), nullable=True)
    status = Column(SAEnum(TradeStatus), default=TradeStatus.OPEN, index=True)
    exit_reason = Column(SAEnum(TradeExitReason), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    portfolio = relationship("MockPortfolio", back_populates="trades")
    recommendation = relationship("Recommendation", back_populates="paper_trades")


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, unique=True)
    exchange = Column(String(10), default="NSE")
    notes = Column(Text, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)


class NewsEvent(Base):
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    headline = Column(Text, nullable=False)
    source = Column(String(100))
    published_at = Column(DateTime)
    sentiment = Column(String(20))  # 'positive' / 'negative' / 'neutral'
    sentiment_label = Column(String(30))  # human-readable: 'strongly positive' etc.
    material_event_type = Column(
        String(50)
    )  # 'earnings' / 'regulatory' / 'promoter' etc.
    is_material = Column(Boolean, default=False)  # True = triggers alert
    alert_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RejectedHeadline(Base):
    __tablename__ = "rejected_headlines"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), index=True)
    headline = Column(Text, nullable=False)
    source = Column(String(50))
    published_at = Column(DateTime)
    filter_status = Column(String(20))  # 'stoplist' | 'no_keyword'
    rejected_at = Column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_rejected_symbol_at", "symbol", "rejected_at"),)


class MarketRegimeSnapshot(Base):
    __tablename__ = "market_regime_snapshots"

    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False, unique=True, index=True)
    nifty_trend = Column(String(20), nullable=False)  # 'BULL' | 'BEAR' | 'SIDEWAYS'
    nifty_slope = Column(Float, nullable=True)  # EMA50 slope (5-day)
    distance_from_ema50_pct = Column(
        Float, nullable=True
    )  # % distance of Close from EMA50
    sector_rs = Column(JSON, nullable=True)  # {sector: rs_vs_nifty}
    created_at = Column(DateTime, default=datetime.utcnow)


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True)
    weekly_run_id = Column(Integer, ForeignKey("weekly_runs.id"), nullable=True)
    symbol = Column(String(20), nullable=False)
    bundle_name = Column(
        String(50), nullable=False
    )  # 'trend' / 'reversal' / 'breakout' / 'smc' / 'composite'
    run_date = Column(Date, nullable=False)
    win_rate = Column(Float)  # 0.0 to 1.0
    avg_return_pct = Column(Float)  # average % return per trade
    max_drawdown_pct = Column(Float)  # peak-to-trough drawdown
    sharpe_ratio = Column(Float)
    total_trades = Column(Integer)
    weight_assigned = Column(Float)  # 0.0 to 1.0 (sum = 1.0 across bundles)
    equity_curve_json = Column(Text, nullable=True)  # JSON: [{date, equity}, ...]
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_backtest_results_bundle_date", "bundle_name", "run_date"),
    )


class TradeOutcomesAudit(Base):
    """One row per closed recommendation — bucket-tagged for calibration."""

    __tablename__ = "trade_outcomes_audit"

    id = Column(Integer, primary_key=True)
    recommendation_id = Column(
        Integer, ForeignKey("recommendations.id"), nullable=False, index=True
    )
    symbol = Column(String(20), nullable=False, index=True)
    outcome = Column(SAEnum(OutcomeVerdict), nullable=False, index=True)
    outcome_pct = Column(Float, nullable=True)
    exit_date = Column(Date, nullable=True)
    mfe_pct = Column(Float, nullable=True)
    mae_pct = Column(Float, nullable=True)
    trading_days_held = Column(Integer, nullable=True)
    score_bucket = Column(String(20), nullable=True, index=True)  # e.g. "70-100"
    bundle_used = Column(String(200), nullable=True)
    regime_at_signal = Column(
        String(20), nullable=True
    )  # BULL/BEAR/SIDEWAYS at signal time
    created_at = Column(DateTime, default=datetime.utcnow)


class WalkForwardRun(Base):
    """One row per IS/OOS window slice in a walk-forward evaluation."""

    __tablename__ = "walk_forward_runs"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    bundle_name = Column(String(50), nullable=False, index=True)
    run_date = Column(Date, nullable=False, index=True)
    window_idx = Column(Integer, nullable=False)  # 0-based window number
    is_start = Column(Date, nullable=False)  # in-sample start date
    is_end = Column(Date, nullable=False)  # in-sample end date
    oos_start = Column(Date, nullable=False)  # out-of-sample start date
    oos_end = Column(Date, nullable=False)  # out-of-sample end date
    is_sharpe = Column(Float, nullable=True)
    oos_sharpe = Column(Float, nullable=True)
    is_trades = Column(Integer, nullable=True)
    oos_trades = Column(Integer, nullable=True)
    is_win_rate = Column(Float, nullable=True)
    oos_win_rate = Column(Float, nullable=True)
    overfit_flag = Column(
        Boolean, default=False
    )  # True if OOS Sharpe drops >50% from IS
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_wfr_symbol_bundle_date", "symbol", "bundle_name", "run_date"),
    )


class TradingParam(Base):
    """
    Editable trading parameters stored in the DB.
    Each row is one key=value pair. Values are stored as strings and
    cast at read time using value_type.
    """

    __tablename__ = "trading_params"

    id = Column(Integer, primary_key=True)
    param_key = Column(String(60), nullable=False, unique=True, index=True)
    value = Column(String(100), nullable=False)
    value_type = Column(
        String(10), nullable=False, default="float"
    )  # 'float' | 'int' | 'str'
    min_allowed = Column(Float, nullable=True)
    max_allowed = Column(Float, nullable=True)
    label = Column(
        String(100), nullable=True
    )  # human-readable label for the Settings form
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(50), nullable=True, default="system")


class TuningSuggestion(Base):
    """
    Auto-generated parameter-tuning suggestion produced by the suggestion loop.
    Surfaces in Settings tab with [Apply] [Reject] [Defer] actions.
    """

    __tablename__ = "tuning_suggestions"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    report_date = Column(Date, nullable=False, index=True)
    dimension = Column(
        String(50), nullable=False, index=True
    )  # 'score_bucket' | 'bundle' | 'regime'
    dimension_value = Column(
        String(50), nullable=False
    )  # e.g. '70-100', 'trend', 'BULL'
    current_win_rate = Column(Float, nullable=False)
    target_win_rate = Column(Float, nullable=False)
    n_trades = Column(Integer, nullable=False)
    suggestion_text = Column(Text, nullable=False)  # human-readable suggestion
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending | applied | rejected | deferred
    applied_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("idx_ts_dimension_date", "dimension", "report_date"),)


class TuningHistory(Base):
    """
    Record of applied tuning changes with before/after metrics.
    Written when a TuningSuggestion is applied.
    """

    __tablename__ = "tuning_history"

    id = Column(Integer, primary_key=True)
    suggestion_id = Column(
        Integer, ForeignKey("tuning_suggestions.id"), nullable=False, index=True
    )
    applied_at = Column(DateTime, default=datetime.utcnow)
    dimension = Column(String(50), nullable=False)
    dimension_value = Column(String(50), nullable=False)
    change_description = Column(Text, nullable=False)
    win_rate_before = Column(Float, nullable=True)
    win_rate_after = Column(Float, nullable=True)  # filled in by next reporting loop
    rollback_after = Column(DateTime, nullable=True)  # set if auto-tuning rolls back
    created_at = Column(DateTime, default=datetime.utcnow)


class AlertType(str, enum.Enum):
    PRE_SL_WARNING = "PRE_SL_WARNING"
    TARGET1_HIT = "TARGET1_HIT"
    TARGET2_HIT = "TARGET2_HIT"
    TREND_INVALIDATED = "TREND_INVALIDATED"


class Alert(Base):
    """
    One row per alert fired for an open position.
    Dedup key: (trade_id, alert_type) within a 1-hour cooldown window.
    """

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    trade_id = Column(
        Integer, ForeignKey("paper_trades.id"), nullable=False, index=True
    )
    portfolio_id = Column(
        Integer, ForeignKey("mock_portfolios.id"), nullable=False, index=True
    )
    symbol = Column(String(20), nullable=False)
    alert_type = Column(SAEnum(AlertType), nullable=False)
    triggered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    message = Column(Text, nullable=False)
    channels_sent = Column(JSON, default=list)  # list of channel names attempted
    acknowledged = Column(Boolean, default=False)
    ltp_at_trigger = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
