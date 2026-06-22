from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_serializer


class AccumulationCandidateOut(BaseModel):
    id: int
    run_id: str
    symbol: str
    score: int
    rs_30: float
    rs_90: float
    rs_180: float
    cagr_eps_3y: float | None
    valuation_pillar_pct: float
    thesis_text: str
    hard_avoid_active: bool
    created_at: datetime


class AccumulationPositionOut(BaseModel):
    id: int
    symbol: str
    state: Literal["BUILDING", "FULL", "PAUSED", "EXITED", "CONVERTED_TO_SWING"]
    avg_cost: Decimal
    qty_total: int
    opened_at: datetime
    last_thesis_check_at: datetime

    @field_serializer("avg_cost")
    def _ser_decimal(self, value: Decimal) -> str:
        return str(value)


class TrancheOut(BaseModel):
    id: int
    position_id: int
    seq: int
    atr_normalized_trigger_pct: float
    filled_at_price: Decimal | None
    filled_at: datetime | None
    thesis_revalidated: bool

    @field_serializer("filled_at_price")
    def _ser_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class PauseIn(BaseModel):
    reason: str


class StartPositionIn(BaseModel):
    symbol: str
    price: Decimal
    qty: int
    note: str = ""


class TrancheFilledIn(BaseModel):
    price: Decimal
    qty: int
    note: str = ""


class ExitPositionIn(BaseModel):
    price: Decimal
    qty: int
    reason: str = "manual"
