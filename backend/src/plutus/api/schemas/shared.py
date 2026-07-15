from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_serializer


class RegimeSnapshotOut(BaseModel):
    as_of_date: date
    label: Literal["BULL", "BEAR", "SIDEWAYS"]
    nifty_close: Decimal
    pct_above_50dma: float
    pct_above_200dma: float
    advance_decline: float
    india_vix: float
    fii_flow_inr: Decimal
    dii_flow_inr: Decimal
    breadth_confirmed_flip: bool

    @field_serializer("nifty_close", "fii_flow_inr", "dii_flow_inr")
    def _ser_decimal(self, value: Decimal) -> str:
        return str(value)


class RegimeVerdictOut(BaseModel):
    """Latest regime view derived from the most recent snapshot."""

    as_of_date: date
    label: Literal["BULL", "BEAR", "SIDEWAYS"]
    india_vix: float
    breadth_confirmed_flip: bool


class CalibrationRowOut(BaseModel):
    bucket: str
    regime: str
    n_closed: int
    win_rate: float
    expectancy_R: float
    ci_low_R: float
    ci_high_R: float
    sprt_state: Literal["accept_H0", "accept_H1", "continue"]
    confidence_band: Literal["low", "medium", "high"]
    last_updated: datetime


class BenchmarkResultOut(BaseModel):
    plutus_net_pct: float
    nifty_net_pct: float
    regime_switched_net_pct: float
    random_liquid_net_pct: float
    plutus_profit_factor: float
    plutus_n_trades: int


class RunOut(BaseModel):
    run_id: str


class ChartBarOut(BaseModel):
    date: str  # ISO date "2024-01-15" for daily, ISO datetime "2024-01-15T09:15:00" for hourly
    open: float
    high: float
    low: float
    close: float
    volume: float
    dma20: float | None = None
    dma50: float | None = None
    dma200: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None
    bb_mid: float | None = None
    ema8: float | None = None
    ema13: float | None = None
    ema21: float | None = None
    ema34: float | None = None
    ema55: float | None = None
    golden_cross_20_50: bool = False


class ChartSignalMarker(BaseModel):
    entry: float
    stop_loss: float
    target_1: float
    target_2: float
    bundle: str


class ChartDataOut(BaseModel):
    symbol: str
    latest_price: float
    latest_change_pct: float
    bars: list[ChartBarOut]
    intraday_bars: list[ChartBarOut] = []
    signal_marker: ChartSignalMarker | None = None


class PositionSnapshotOut(BaseModel):
    symbol: str
    mode: str  # "swing" or "accumulation"
    qty: int
    avg_cost: float
    current_price: float
    pnl: float
    pnl_pct: float
    stop_loss: float | None = None
    sl_distance_pct: float | None = None
    # Per-lot identity: populated for swing trades (one row per SwingTrade) so the
    # frontend can group multi-lot positions by symbol and dispatch actions to the
    # right specific trade. None for accumulation, which is inherently one-per-symbol.
    trade_id: int | None = None
    opened_at: datetime | None = None


class PortfolioSnapshotOut(BaseModel):
    positions: list[PositionSnapshotOut]
    total_invested: float
    total_current: float
    total_pnl: float
    total_pnl_pct: float
    # Realised P/L across all closed swing trades — derived from BUY/SELL fill
    # rows on every request so it reflects the latest manual exit immediately
    # (the WeeklyPostmortem row it used to read from only refreshes once a week).
    total_realized_pnl: float = 0.0
    total_realized_pct: float = 0.0
    n_closed_trades: int = 0
    checked_at: datetime


class NotificationOut(BaseModel):
    id: int
    kind: str
    severity: str
    title: str
    body: str
    symbol: str | None
    dismissed: bool
    created_at: datetime


class AiSummaryOut(BaseModel):
    kind: str
    cache_key: str
    content: str
    model: str
    created_at: datetime
    cached: bool
    available: bool  # False when no OPENROUTER_API_KEY is configured


class NewsItemOut(BaseModel):
    symbol: str
    title: str
    snippet: str
    url: str
    source: str
    published_at: str
    sentiment_score: float | None
    sentiment: str  # 'positive' | 'negative' | 'neutral'
    sector: str | None = None


class SignalNewsOut(BaseModel):
    items: list[NewsItemOut]
    symbols: list[str]  # signal symbols sectors were resolved for
    sectors: list[str]  # top sectors the news was fetched for
    fetched_at: datetime
    cached: bool
    available: bool  # False when no MARKETAUX_API_KEY is configured


class HealthOut(BaseModel):
    ok: bool


class VersionOut(BaseModel):
    version: str


class RunLogRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    job_name: str
    started_at: datetime
    ended_at: datetime | None
    status: str | None
    details_json: dict[str, Any] | None


class BacktestRequestIn(BaseModel):
    bundle: str
    symbol: str
    lookback_days: int = 365
    use_cost_model: bool = True
    use_fill_policy: bool = True


class BacktestTradeOut(BaseModel):
    entry_date: str
    exit_date: str
    hold_days: int
    realized_R: float


class BacktestResultOut(BaseModel):
    bundle: str
    symbol: str
    start: date
    end: date
    n_trades: int
    win_rate: float
    expectancy_R: float
    sum_R: float
    avg_hold_days: float
    fills_before_signal: int
    cost_model_on: bool
    fill_policy_on: bool
    trades: list[BacktestTradeOut]
