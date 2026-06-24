from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from plutus.config.settings import Settings
from plutus.shared.calibration.deadzone import is_in_soft_dead_zone
from plutus.swing.scoring.expectancy import ExpectancyResult

Label = Literal["BUY", "BUY_WATCH", "WATCH", "HOLD", "AVOID"]


@dataclass(frozen=True)
class ClassificationOutput:
    label: Label
    score: int
    soft_dead_zone: bool
    calibration_band: Literal["low", "medium", "high"]
    counterfactual: str


def classify(
    score: int,
    expectancy: ExpectancyResult,
    calibration_band: Literal["low", "medium", "high"],
    settings: Settings,
    *,
    hard_avoid: bool = False,
) -> ClassificationOutput:
    """Spec 07 §8 banding.

    - AVOID if a hard-avoid pillar fires OR expectancy_R < 0.
    - HOLD if expectancy fails both primary and fallback gates.
    - WATCH if score < soft_dead_zone_lower.
    - BUY_WATCH if score in [lower, upper] (B17 soft dead zone).
    - BUY if score > upper AND expectancy primary gate passes.
    """
    dead_zone = is_in_soft_dead_zone(score, settings)

    if hard_avoid or expectancy.expectancy_R < 0:
        return ClassificationOutput(
            "AVOID",
            score,
            dead_zone,
            calibration_band,
            _counterfactual("AVOID", score, expectancy, settings),
        )

    if not expectancy.passes_primary_gate and not expectancy.passes_fallback_gate:
        return ClassificationOutput(
            "HOLD",
            score,
            dead_zone,
            calibration_band,
            _counterfactual("HOLD", score, expectancy, settings),
        )

    if score < settings.soft_dead_zone_lower:
        label: Label = "WATCH"
    elif dead_zone:
        label = "BUY_WATCH"
    elif expectancy.passes_primary_gate:
        label = "BUY"
    else:
        label = "BUY_WATCH"

    return ClassificationOutput(
        label,
        score,
        dead_zone,
        calibration_band,
        _counterfactual(label, score, expectancy, settings),
    )


def _counterfactual(
    label: Label, score: int, expectancy: ExpectancyResult, settings: Settings
) -> str:
    if label == "BUY_WATCH":
        gap = settings.soft_dead_zone_upper + 1 - score
        if gap > 0:
            return f"+{gap} score points would flip BUY_WATCH -> BUY"
        return "a positive expectancy primary-gate pass would flip BUY_WATCH -> BUY"
    if label == "AVOID":
        return "a positive net expectancy and no hard-avoid would move AVOID -> HOLD"
    if label == "HOLD":
        deficit = settings.expectancy_floor_R - expectancy.expectancy_R
        return f"+{deficit:.2f}R net expectancy would move HOLD -> a tradable band"
    return ""
