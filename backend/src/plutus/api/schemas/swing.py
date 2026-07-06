from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_serializer


class PillarBreakdownOut(BaseModel):
    technical: int
    expectancy: float
    flow: int
    regime_fit: int
    fundamentals: int
    sentiment: int


class SwingSignalOut(BaseModel):
    id: int
    run_id: str
    symbol: str
    bundle: str
    score: int
    label: Literal["BUY", "BUY_WATCH", "WATCH", "HOLD", "AVOID"]
    entry: Decimal
    stop_loss: Decimal
    target_1: Decimal
    target_2: Decimal
    expectancy_R: float
    drawn_rr: float
    regime_at_signal: str
    pillar_breakdown: PillarBreakdownOut
    counterfactual: str | None
    calibration_band: Literal["low", "medium", "high"]
    created_at: datetime

    @field_serializer("entry", "stop_loss", "target_1", "target_2")
    def _ser_decimal(self, value: Decimal) -> str:
        return str(value)


class SwingTradeOut(BaseModel):
    id: int
    signal_id: int
    symbol: str
    bundle: str
    state: Literal["OPEN", "T1_HIT", "CLOSED_WIN", "CLOSED_LOSS", "SCRATCHED", "EXPIRED"]
    opened_at: datetime
    closed_at: datetime | None
    qty: int
    risk_R: float
    exit_reason: str | None
    realized_R: float | None
    mfe_R: float | None
    mae_R: float | None


class FillOut(BaseModel):
    id: int
    trade_id: int
    kind: Literal["MOCK", "REAL"]
    side: Literal["BUY", "SELL"]
    qty: int
    price: Decimal
    cost_inr: Decimal
    slippage_bps: float | None
    filled_at: datetime

    @field_serializer("price", "cost_inr")
    def _ser_decimal(self, value: Decimal) -> str:
        return str(value)


class RealFillIn(BaseModel):
    side: Literal["BUY", "SELL"]
    qty: int
    price: Decimal
    cost_inr: Decimal = Decimal("0")
    filled_at: datetime | None = None


class EnterFromSignalIn(BaseModel):
    """Create a SwingTrade + real entry fill from a signal id in one shot."""

    side: Literal["BUY", "SELL"] = "BUY"
    qty: int
    price: Decimal
    cost_inr: Decimal = Decimal("0")
    filled_at: datetime | None = None


class ManualExitIn(BaseModel):
    reason: str


class CooldownRowOut(BaseModel):
    id: int
    symbol: str
    kind: Literal["SL_BREACH", "SL_WARNING", "T1_HIT", "NO_PROGRESS"]
    last_fired_at: datetime


class PostmortemOut(BaseModel):
    week_ending: str
    swing_return_pct: float
    nifty_return_pct: float
    regime_switched_return_pct: float
    random_baseline_return_pct: float
    n_swing_trades_closed: int
    drawdown_pct: float
    report_md_path: str
