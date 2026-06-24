from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from plutus.accumulation.fundamentals.hard_avoid import (
    FundamentalsSnapshot,
    HardAvoid,
    HardAvoidResult,
)
from plutus.accumulation.fundamentals.quality import Quality
from plutus.accumulation.fundamentals.valuation import Valuation, ValuationInputs
from plutus.accumulation.rs.blend import RSBlendResult
from plutus.accumulation.scoring.classifier import (
    AccumulationClassifier,
    AccumulationLabel,
)
from plutus.accumulation.scoring.pillars import AccumulationPillars, compose_pillars
from plutus.config.settings import Settings


@dataclass(frozen=True)
class FundamentalsScore:
    pillars: AccumulationPillars
    label: AccumulationLabel
    hard_avoid: HardAvoidResult


class FundamentalsScorer:
    """Composes the four accumulation pillars (spec 08 §2) and classifies (§8)."""

    def __init__(self, settings: Settings) -> None:
        self._quality = Quality()
        self._valuation = Valuation()
        self._hard_avoid = HardAvoid(settings)
        self._classifier = AccumulationClassifier()

    def score(
        self,
        snapshot: FundamentalsSnapshot,
        valuation_inputs: ValuationInputs,
        earnings_history: pd.DataFrame,
        rs_blend: RSBlendResult,
    ) -> FundamentalsScore:
        quality_points = self._quality.score(
            roce=snapshot.roce, de=snapshot.de, fcf_margin=snapshot.fcf_margin
        )
        growth_points = self._valuation.growth_score(earnings_history)
        valuation_points = self._valuation.score(valuation_inputs)

        pillars = compose_pillars(
            quality=quality_points,
            growth=growth_points,
            valuation=valuation_points,
            blended_rs=rs_blend.blended,
        )
        hard_avoid = self._hard_avoid.evaluate(snapshot)
        label = self._classifier.classify(
            pillars.total, pillars.quality, hard_avoid
        )
        return FundamentalsScore(pillars=pillars, label=label, hard_avoid=hard_avoid)
