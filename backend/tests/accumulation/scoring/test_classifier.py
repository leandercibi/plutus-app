from __future__ import annotations

from plutus.accumulation.fundamentals.hard_avoid import HardAvoidResult
from plutus.accumulation.scoring.classifier import (
    AccumulationClassifier,
    AccumulationLabel,
)


def _clean() -> HardAvoidResult:
    return HardAvoidResult(avoid=False, reasons=[])


def _avoid() -> HardAvoidResult:
    return HardAvoidResult(avoid=True, reasons=["D/E breach"])


def _classify(score: int, quality: int, hard_avoid: HardAvoidResult) -> AccumulationLabel:
    return AccumulationClassifier().classify(score, quality, hard_avoid)


def test_hard_avoid_is_avoid_regardless_of_score() -> None:
    assert _classify(95, 28, _avoid()) == "AVOID"


def test_below_60_is_watch() -> None:
    assert _classify(55, 20, _clean()) == "WATCH"


def test_60_to_75_is_build_slowly() -> None:
    assert _classify(60, 20, _clean()) == "BUILD_SLOWLY"
    assert _classify(74, 21, _clean()) == "BUILD_SLOWLY"


def test_accumulate_now_requires_score_and_quality() -> None:
    assert _classify(78, 24, _clean()) == "ACCUMULATE_NOW"


def test_high_score_low_quality_is_build_slowly_not_accumulate() -> None:
    # score >= 75 but quality pillar < 22 -> not ACCUMULATE_NOW
    assert _classify(80, 18, _clean()) == "BUILD_SLOWLY"
