from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal
from plutus.swing.bundles._indicators import atr, delivery_adjusted_volume
from plutus.swing.bundles.base import BaseBundle, BundleContext, RequiredInput

_ATR_PERIOD = 14
_MIN_CONTRACTIONS = 3
_CONTRACTION_LEN = 8
_VOLUME_MULT = 1.3
_STOP_ATR_BUFFER = Decimal("0.5")
_T1_RR = Decimal("2.0")
_T2_RR = Decimal("3.0")


class VCPBundle(BaseBundle):
    """Spec 07 §3.4. Minervini volatility contraction: >= 3 contractions of
    decreasing amplitude on declining volume, breakout from the final
    contraction on expanding delivery-adjusted volume. Circuit-affected bars
    (ctx.extras['circuit_bars']) are excluded from the contraction count (B7)."""

    name: ClassVar[str] = "vcp"
    horizon_days: ClassVar[tuple[int, int]] = (5, 25)

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def required_inputs(self) -> set[RequiredInput]:
        return {"ohlcv", "delivery"}

    def fit_signal(
        self, symbol: str, candles: pd.DataFrame, ctx: BundleContext
    ) -> BundleSignal | None:
        if ctx.delivery is None:
            return None

        atr_series = atr(candles, _ATR_PERIOD)
        last_atr = atr_series.iloc[-1]
        if pd.isna(last_atr) or last_atr <= 0:
            return None

        raw_circuit = ctx.extras.get("circuit_bars", set())
        circuit_bars: set[int] = set(raw_circuit) if isinstance(raw_circuit, (set, list)) else set()

        # the pre-breakout history: all bars except the last (breakout) bar
        history = candles.iloc[:-1].reset_index(drop=True)
        usable_idx = [i for i in range(len(history)) if i not in circuit_bars]
        if len(usable_idx) < _MIN_CONTRACTIONS * _CONTRACTION_LEN:
            return None

        usable = history.iloc[usable_idx].reset_index(drop=True)

        # split usable bars into consecutive contraction windows
        ranges: list[float] = []
        volumes: list[float] = []
        n_windows = len(usable) // _CONTRACTION_LEN
        for w in range(n_windows):
            chunk = usable.iloc[w * _CONTRACTION_LEN : (w + 1) * _CONTRACTION_LEN]
            ranges.append(float((chunk["high"] - chunk["low"]).mean()))
            volumes.append(float(chunk["volume"].mean()))

        if len(ranges) < _MIN_CONTRACTIONS:
            return None

        # use the last N windows; require decreasing amplitude and declining volume
        recent_ranges = ranges[-_MIN_CONTRACTIONS:]
        recent_volumes = volumes[-_MIN_CONTRACTIONS:]
        amplitude_decreasing = all(
            recent_ranges[i] > recent_ranges[i + 1] for i in range(len(recent_ranges) - 1)
        )
        volume_declining = all(
            recent_volumes[i] > recent_volumes[i + 1] for i in range(len(recent_volumes) - 1)
        )
        if not (amplitude_decreasing and volume_declining):
            return None

        # breakout bar: clears the final contraction high on expanding delivery volume
        final_contraction_high = usable["high"].iloc[-_CONTRACTION_LEN:].max()
        price = candles["close"].iloc[-1]
        if not (price > final_contraction_high):
            return None

        dav = delivery_adjusted_volume(ctx.delivery)
        median_dav = dav.iloc[:-1].median()
        if not (dav.iloc[-1] > _VOLUME_MULT * median_dav):
            return None

        entry = Decimal(str(price))
        stop = Decimal(str(final_contraction_high)) - _STOP_ATR_BUFFER * Decimal(str(last_atr))
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
                "three_contractions",
                "declining_volume",
                "delivery_volume_breakout",
            ),
        )
