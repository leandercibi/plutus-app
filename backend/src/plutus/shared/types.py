from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class BundleSignal:
    """A candidate signal produced by a bundle's fit_signal. Carries geometry and
    a per-bundle internal score that is NOT used for classification (A3)."""

    symbol: str
    bundle: str
    as_of: date
    entry: Decimal
    stop_loss: Decimal
    target_1: Decimal
    target_2: Decimal
    reasons: tuple[str, ...] = ()
    internal_score: float = 0.0


@dataclass(frozen=True)
class BacktestTrade:
    symbol: str
    bundle: str
    regime: str
    entry_date: date
    exit_date: date
    realized_R: float
    hold_days: int


@dataclass(frozen=True)
class BundleStats:
    bundle: str
    regime: str | Literal["ALL"]
    n_trades: int
    win_rate: float
    expectancy_R: float
    sharpe_raw: float
    ci_low_R: float
    ci_high_R: float
