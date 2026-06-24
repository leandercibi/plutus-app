from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.fills.policy import FillPolicy, FillResult
from plutus.shared.fills.types import OHLCBar, TradePlan
from plutus.swing.exits.no_progress import NoProgressExit, NoProgressInput
from plutus.swing.exits.stop import StopExit

ExitAction = Literal["STOP", "NO_PROGRESS", "HOLD"]


@dataclass(frozen=True)
class OpenTradeView:
    plan: TradePlan
    entry_idx: int
    current_idx: int
    horizon_max_days: int
    adv: int
    atr_pct: float
    qty: int = 1


@dataclass(frozen=True)
class ExitDecision:
    action: ExitAction
    reason: str
    fill: FillResult | None


class ExitManager:
    """Owns the daily exit-check loop. Priority: stop -> trailing -> no_progress.

    Trailing tightens the working stop level; the stop check then decides on the bar.
    On a same-bar conflict the stop wins because it is evaluated first.
    """

    def __init__(self, settings: Settings, fills: FillPolicy) -> None:
        self._stop = StopExit()
        self._no_progress = NoProgressExit(settings)
        self._fills = fills

    def tick(
        self, view: OpenTradeView, candles: pd.DataFrame, today_bar: OHLCBar
    ) -> ExitDecision:
        stop_fill = self._stop.check(
            view.plan, today_bar, self._fills, view.adv, view.atr_pct, view.qty
        )
        if stop_fill is not None:
            return ExitDecision("STOP", "stop-loss breached", stop_fill)

        np_input = NoProgressInput(
            entry=view.plan.entry,
            stop_loss=view.plan.stop_loss,
            target_1=view.plan.target_1,
            entry_idx=view.entry_idx,
            current_idx=view.current_idx,
            horizon_max_days=view.horizon_max_days,
        )
        if self._no_progress.should_exit(np_input, candles):
            return ExitDecision(
                "NO_PROGRESS", "no progress toward T1 by midpoint", None
            )

        return ExitDecision("HOLD", "no exit condition met", None)
