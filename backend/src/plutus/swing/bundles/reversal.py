from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal
from plutus.swing.bundles._indicators import atr, delivery_adjusted_volume, sma
from plutus.swing.bundles.base import BaseBundle, BundleContext, RequiredInput

_DMA_WINDOW = 20
_ATR_PERIOD = 14
_DOWN_CLOSES_REQUIRED = 5
_VOLUME_MULT = 1.3
_STOP_ATR_BUFFER = Decimal("0.5")
_T1_RR = Decimal("1.5")
_T2_RR = Decimal("2.5")


class ReversalBundle(BaseBundle):
    """Spec 07 §3.3. Five closes below the 20DMA, then a bullish engulfing
    candle confirmed by delivery-adjusted volume."""

    name: ClassVar[str] = "reversal"
    horizon_days: ClassVar[tuple[int, int]] = (3, 12)

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def required_inputs(self) -> set[RequiredInput]:
        return {"ohlcv", "delivery"}

    def fit_signal(
        self, symbol: str, candles: pd.DataFrame, ctx: BundleContext
    ) -> BundleSignal | None:
        if (
            ctx.delivery is None
            or len(candles) < _DMA_WINDOW + _DOWN_CLOSES_REQUIRED + 1
        ):
            return None

        close = candles["close"]
        open_ = candles["open"]
        dma20 = sma(close, _DMA_WINDOW)
        atr_series = atr(candles, _ATR_PERIOD)
        last_atr = atr_series.iloc[-1]
        if pd.isna(last_atr) or last_atr <= 0:
            return None

        # 5 closes below the 20DMA in the window preceding the engulfing bar
        prior_closes = close.iloc[-(_DOWN_CLOSES_REQUIRED + 1) : -1]
        prior_dma = dma20.iloc[-(_DOWN_CLOSES_REQUIRED + 1) : -1]
        if not (prior_closes < prior_dma).all():
            return None

        # bullish engulfing: today's body engulfs the prior body
        prev_open = open_.iloc[-2]
        prev_close = close.iloc[-2]
        today_open = open_.iloc[-1]
        today_close = close.iloc[-1]
        bullish_engulfing = (
            prev_close < prev_open  # prior bar bearish
            and today_close > today_open  # today bullish
            and today_open <= prev_close
            and today_close >= prev_open
        )
        if not bullish_engulfing:
            return None

        # delivery-adjusted volume confirmation on the engulfing bar
        dav = delivery_adjusted_volume(ctx.delivery)
        median_dav = dav.iloc[-(_DMA_WINDOW + 1) : -1].median()
        if not (dav.iloc[-1] > _VOLUME_MULT * median_dav):
            return None

        entry = Decimal(str(today_close))
        engulf_low = candles["low"].iloc[-1]
        stop = Decimal(str(engulf_low)) - _STOP_ATR_BUFFER * Decimal(str(last_atr))
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
            reasons=(
                "five_closes_below_20dma",
                "bullish_engulfing",
                "delivery_volume_confirm",
            ),
        )
