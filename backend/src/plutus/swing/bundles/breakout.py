from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal
from plutus.swing.bundles._indicators import atr, delivery_adjusted_volume
from plutus.swing.bundles.base import BaseBundle, BundleContext, RequiredInput

_DONCHIAN_WINDOW = 20
_ATR_PERIOD = 14
_VOLUME_MULT = 1.5
_STOP_ATR_BUFFER = 1.5
_T1_RR = 1.5
_T2_RR = 2.5


class BreakoutBundle(BaseBundle):
    """Spec 07 §3.2. Donchian-20 high cleared with delivery-adjusted volume
    > 1.5x the 20-day median. B7: a recent circuit hit suppresses the setup
    unless the breakout move exceeds settings.breakout_strong_atr_mult ATR."""

    name: ClassVar[str] = "breakout"
    horizon_days: ClassVar[tuple[int, int]] = (3, 15)

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def required_inputs(self) -> set[RequiredInput]:
        return {"ohlcv", "delivery", "bulk_block"}

    def fit_signal(
        self, symbol: str, candles: pd.DataFrame, ctx: BundleContext
    ) -> BundleSignal | None:
        if ctx.delivery is None or len(candles) < _DONCHIAN_WINDOW + 1:
            return None

        close = candles["close"]
        atr_series = atr(candles, _ATR_PERIOD)
        last_atr = atr_series.iloc[-1]
        if pd.isna(last_atr) or last_atr <= 0:
            return None

        # Donchian-20 high computed over the bars BEFORE today
        donchian_high = candles["high"].iloc[-(_DONCHIAN_WINDOW + 1) : -1].max()
        price = close.iloc[-1]
        if not (price > donchian_high):
            return None

        # delivery-adjusted volume expansion on the breakout bar
        dav = delivery_adjusted_volume(ctx.delivery)
        median_dav = dav.iloc[-(_DONCHIAN_WINDOW + 1) : -1].median()
        if not (dav.iloc[-1] > _VOLUME_MULT * median_dav):
            return None

        breakout_atr_distance = (price - donchian_high) / last_atr

        # B7 circuit hook
        if ctx.extras.get("circuit_recent_hit") and (
            breakout_atr_distance <= self._settings.breakout_strong_atr_mult
        ):
            return None

        entry = Decimal(str(price))
        stop = Decimal(str(donchian_high)) - Decimal(str(_STOP_ATR_BUFFER)) * Decimal(str(last_atr))
        risk = entry - stop
        target_1 = entry + Decimal(str(_T1_RR)) * risk
        target_2 = entry + Decimal(str(_T2_RR)) * risk

        return BundleSignal(
            symbol=symbol,
            bundle=self.name,
            as_of=candles["date"].iloc[-1].date(),
            entry=entry,
            stop_loss=stop,
            target_1=target_1,
            target_2=target_2,
            reasons=("donchian20_break", "delivery_volume_expansion"),
        )
