from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal
from plutus.swing.bundles._indicators import atr
from plutus.swing.bundles.base import BaseBundle, BundleContext, RequiredInput

_ATR_PERIOD = 14
_STOP_ATR_MULT = Decimal("1.5")
_T1_RR = Decimal("1.5")
_T2_RR = Decimal("2.5")


class PEADBundle(BaseBundle):
    """Spec 07 §3.6 (C2 gated). Runs only when earnings occurred in the last 5
    sessions AND the verified-earnings flag is set. Paper-only until evidence."""

    name: ClassVar[str] = "pead"
    horizon_days: ClassVar[tuple[int, int]] = (3, 15)

    def __init__(self, settings: Settings, paper_only: bool = True) -> None:
        self._settings = settings
        self._paper_only = paper_only

    def required_inputs(self) -> set[RequiredInput]:
        return {"ohlcv", "earnings"}

    def fit_signal(
        self, symbol: str, candles: pd.DataFrame, ctx: BundleContext
    ) -> BundleSignal | None:
        if not ctx.extras.get("earnings_in_last_5_sessions"):
            return None
        if not ctx.extras.get("verified_earnings"):
            return None

        atr_series = atr(candles, _ATR_PERIOD)
        last_atr = atr_series.iloc[-1]
        if pd.isna(last_atr) or last_atr <= 0:
            return None

        price = candles["close"].iloc[-1]
        entry = Decimal(str(price))
        stop = entry - _STOP_ATR_MULT * Decimal(str(last_atr))
        risk = entry - stop
        target_1 = entry + _T1_RR * risk
        target_2 = entry + _T2_RR * risk

        reasons: tuple[str, ...] = ("earnings_drift", "verified_earnings")
        if self._paper_only:
            reasons = reasons + ("paper_only",)

        return BundleSignal(
            symbol=symbol,
            bundle=self.name,
            as_of=candles["date"].iloc[-1].date(),
            entry=entry,
            stop_loss=stop,
            target_1=target_1,
            target_2=target_2,
            reasons=reasons,
        )
