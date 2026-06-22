from __future__ import annotations

from typing import Literal

from plutus.accumulation.fundamentals.hard_avoid import HardAvoidResult

AccumulationLabel = Literal["ACCUMULATE_NOW", "BUILD_SLOWLY", "WATCH", "AVOID"]

# Spec 08 §8 thresholds.
_WATCH_CEILING = 60
_BUILD_CEILING = 75
_ACCUMULATE_QUALITY_FLOOR = 22


class AccumulationClassifier:
    """Spec 08 §8 — maps pillar total + quality pillar + hard-avoid into a label."""

    def classify(
        self,
        pillar_score: int,
        quality_score: int,
        hard_avoid: HardAvoidResult,
    ) -> AccumulationLabel:
        if hard_avoid.avoid:
            return "AVOID"
        if pillar_score < _WATCH_CEILING:
            return "WATCH"
        if pillar_score < _BUILD_CEILING:
            return "BUILD_SLOWLY"
        # score >= 75
        if quality_score >= _ACCUMULATE_QUALITY_FLOOR:
            return "ACCUMULATE_NOW"
        return "BUILD_SLOWLY"
