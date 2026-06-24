from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal
from plutus.swing.bundles._indicators import (
    atr,
    delivery_adjusted_volume,
    sma,
)
from plutus.swing.bundles.base import BaseBundle, BundleContext, RequiredInput

_ATR_PERIOD = 14
_PULLBACK_WINDOW = 10
_SWING_HIGH_WINDOW = 20
_STOP_ATR_BUFFER = Decimal("0.5")
_T2_RR = Decimal("1.5")


class TrendBundle(BaseBundle):
    """Spec 07 §3.1. 50DMA>200DMA, price pulled back to 50DMA within 1 ATR,
    delivery-adjusted volume contraction during the pullback."""

    name: ClassVar[str] = "trend"
    horizon_days: ClassVar[tuple[int, int]] = (5, 20)

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def required_inputs(self) -> set[RequiredInput]:
        return {"ohlcv", "delivery"}

    def fit_signal(
        self, symbol: str, candles: pd.DataFrame, ctx: BundleContext
    ) -> BundleSignal | None:
        if ctx.delivery is None or len(candles) < 200:
            return None

        close = candles["close"]
        dma50 = sma(close, 50)
        dma200 = sma(close, 200)
        atr_series = atr(candles, _ATR_PERIOD)

        last_atr = atr_series.iloc[-1]
        if pd.isna(last_atr) or last_atr <= 0:
            return None

        # 1. uptrend structure
        if not (dma50.iloc[-1] > dma200.iloc[-1]):
            return None

        # 2. price pulled back to within 1 ATR of the 50DMA
        price = close.iloc[-1]
        distance_to_dma50 = abs(price - dma50.iloc[-1])
        if distance_to_dma50 > last_atr:
            return None

        # 3. delivery-adjusted volume contraction during the pullback window
        dav = delivery_adjusted_volume(ctx.delivery)
        recent_dav = dav.iloc[-_PULLBACK_WINDOW:].mean()
        prior_dav = dav.iloc[-(_PULLBACK_WINDOW * 3) : -_PULLBACK_WINDOW].mean()
        if not (recent_dav < prior_dav):
            return None

        pullback_low = candles["low"].iloc[-_PULLBACK_WINDOW:].min()
        entry = Decimal(str(price))
        stop = Decimal(str(pullback_low)) - _STOP_ATR_BUFFER * Decimal(str(last_atr))
        swing_high = candles["high"].iloc[-_SWING_HIGH_WINDOW:].max()
        target_1 = Decimal(str(swing_high))
        risk = entry - stop
        target_2 = entry + _T2_RR * risk

        # guard against degenerate geometry (T1 not above entry)
        if target_1 <= entry:
            target_1 = entry + risk

        return BundleSignal(
            symbol=symbol,
            bundle=self.name,
            as_of=candles["date"].iloc[-1].date(),
            entry=entry,
            stop_loss=stop,
            target_1=target_1,
            target_2=target_2,
            reasons=(
                "50dma_gt_200dma",
                "pullback_to_50dma",
                "delivery_volume_contraction",
            ),
        )
