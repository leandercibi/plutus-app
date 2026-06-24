from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from plutus.config.settings import Settings


@dataclass(frozen=True)
class NoProgressInput:
    entry: Decimal
    stop_loss: Decimal
    target_1: Decimal
    entry_idx: int
    current_idx: int
    horizon_max_days: int


class NoProgressExit:
    """B8 — unified no-progress rule.

    Exit (scratch) when realized R toward T1 is below settings.no_progress_t1_threshold
    AND elapsed fraction of the hold window has reached settings.no_progress_elapsed_threshold.
    """

    def __init__(self, settings: Settings) -> None:
        self._t1_threshold = settings.no_progress_t1_threshold
        self._elapsed_threshold = settings.no_progress_elapsed_threshold

    def should_exit(self, inp: NoProgressInput, candles: pd.DataFrame) -> bool:
        elapsed_days = inp.current_idx - inp.entry_idx
        if inp.horizon_max_days <= 0:
            return False
        elapsed_pct = elapsed_days / inp.horizon_max_days
        if elapsed_pct < self._elapsed_threshold:
            return False

        risk_per_share = inp.entry - inp.stop_loss
        if risk_per_share <= 0:
            return False

        current_close = Decimal(str(candles["close"].iloc[inp.current_idx]))
        realized_move = current_close - inp.entry
        # realized R = profit so far measured in risk units (R)
        realized_r = float(realized_move / risk_per_share)
        return realized_r < self._t1_threshold
