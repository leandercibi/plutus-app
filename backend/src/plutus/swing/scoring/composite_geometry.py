from __future__ import annotations

import statistics
from decimal import Decimal
from typing import Literal

from plutus.shared.calibration.protocol import CalibrationLookup, HitField
from plutus.shared.types import BundleSignal


def widest_stop(sub_signals: list[BundleSignal]) -> Decimal:
    """A5. For longs, the widest stop is the lowest stop price (most risk).

    Two sub-signals -> the wider of the two. Three or more -> the median
    (closer to widest than tightest), per spec 07 §6.
    """
    stops = sorted(s.stop_loss for s in sub_signals)
    if len(stops) <= 2:
        return stops[0]
    return Decimal(str(statistics.median(stops)))


def probability_weighted_target(
    sub_signals: list[BundleSignal],
    target_field: Literal["target_1", "target_2"],
    calibration: CalibrationLookup,
    regime: str,
) -> Decimal:
    """A5. weight_i = calibration hit rate for (bundle_i, regime, target_field).

    target = sum(weight_i * target_i) / sum(weight_i).
    """
    hit_field: HitField = target_field
    weighted_sum = Decimal("0")
    weight_total = Decimal("0")
    for s in sub_signals:
        weight = Decimal(str(calibration.hit_rate(s.bundle, regime, hit_field)))
        target = s.target_1 if target_field == "target_1" else s.target_2
        weighted_sum += weight * target
        weight_total += weight
    if weight_total == 0:
        equal = [
            s.target_1 if target_field == "target_1" else s.target_2
            for s in sub_signals
        ]
        return sum(equal, Decimal("0")) / Decimal(len(equal))
    return weighted_sum / weight_total
