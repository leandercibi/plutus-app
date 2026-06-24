from __future__ import annotations

from typing import ClassVar

import pandas as pd

from plutus.shared.calibration.protocol import CalibrationLookup
from plutus.shared.types import BundleSignal
from plutus.swing.bundles.base import BaseBundle, BundleContext, RequiredInput
from plutus.swing.scoring.composite_geometry import (
    probability_weighted_target,
    widest_stop,
)

_MIN_AGREEING = 2
_AGREEING_BUNDLES = {"trend", "breakout", "vcp", "reversal"}


class CompositeBundle(BaseBundle):
    """Spec 07 §3.5 (A5). Aggregates 2+ agreeing sub-bundles using the widest
    structural stop and probability-weighted targets. Never tightest-stop +
    nearest-target."""

    name: ClassVar[str] = "composite"
    horizon_days: ClassVar[tuple[int, int]] = (5, 20)

    def __init__(self, calibration: CalibrationLookup, regime: str) -> None:
        self._calibration = calibration
        self._regime = regime

    def required_inputs(self) -> set[RequiredInput]:
        return {"ohlcv", "delivery"}

    def combine(self, sub_signals: list[BundleSignal]) -> BundleSignal | None:
        agreeing = [s for s in sub_signals if s.bundle in _AGREEING_BUNDLES]
        if len(agreeing) < _MIN_AGREEING:
            return None

        entry = agreeing[0].entry
        stop = widest_stop(agreeing)
        target_1 = probability_weighted_target(
            agreeing, "target_1", self._calibration, self._regime
        )
        target_2 = probability_weighted_target(
            agreeing, "target_2", self._calibration, self._regime
        )

        return BundleSignal(
            symbol=agreeing[0].symbol,
            bundle=self.name,
            as_of=agreeing[0].as_of,
            entry=entry,
            stop_loss=stop,
            target_1=target_1,
            target_2=target_2,
            reasons=tuple(f"agree_{s.bundle}" for s in agreeing),
        )

    def fit_signal(
        self, symbol: str, candles: pd.DataFrame, ctx: BundleContext
    ) -> BundleSignal | None:
        sub_signals = ctx.extras.get("sub_signals")
        if not isinstance(sub_signals, list):
            return None
        return self.combine(sub_signals)
