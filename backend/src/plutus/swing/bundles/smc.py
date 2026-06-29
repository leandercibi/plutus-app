from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal
from plutus.swing.bundles._indicators import atr
from plutus.swing.bundles.base import BaseBundle, BundleContext, RequiredInput

_ATR_PERIOD = 14
_LOOKBACK = 40
_STOP_ATR_MULT = Decimal("2.0")
_T1_RR = Decimal("2.0")
_T2_RR = Decimal("3.0")


class SMCBundle(BaseBundle):
    """Spec 07 §3.7 (C3 gated). May produce a signal but it is display-only by
    default — the selector excludes it from live seeding (tested in selector
    tests, not here)."""

    name: ClassVar[str] = "smc"
    horizon_days: ClassVar[tuple[int, int]] = (5, 20)

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def required_inputs(self) -> set[RequiredInput]:
        return {"ohlcv"}

    def fit_signal(
        self, symbol: str, candles: pd.DataFrame, ctx: BundleContext
    ) -> BundleSignal | None:
        if len(candles) < _LOOKBACK:
            return None

        atr_series = atr(candles, _ATR_PERIOD)
        last_atr = atr_series.iloc[-1]
        if pd.isna(last_atr) or last_atr <= 0:
            return None

        # order-block reclaim: price has reclaimed above the recent swing low zone
        recent_low = candles["low"].iloc[-_LOOKBACK:].min()
        price = candles["close"].iloc[-1]
        if not (price > recent_low):
            return None

        entry = Decimal(str(price))
        stop = entry - _STOP_ATR_MULT * Decimal(str(last_atr))
        risk = entry - stop
        target_1 = entry + _T1_RR * risk
        target_2 = entry + _T2_RR * risk

        return BundleSignal(
            symbol=symbol,
            bundle=self.name,
            as_of=candles["date"].iloc[-1].date(),
            entry=entry,
            stop_loss=stop,
            target_1=target_1,
            target_2=target_2,
            reasons=("order_block_reclaim", "display_only"),
        )
