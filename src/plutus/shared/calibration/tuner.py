from __future__ import annotations

from dataclasses import dataclass

from plutus.config.settings import Settings
from plutus.shared.calibration.ci import bootstrap_R_interval
from plutus.shared.calibration.multiple_testing import benjamini_hochberg
from plutus.shared.calibration.regime_partition import TradeOutcome
from plutus.shared.calibration.sprt import SPRT


@dataclass(frozen=True)
class TunerProposal:
    bundle: str
    regime: str
    parameter: str
    old_value: float
    proposed_value: float
    sprt_state: str
    family_corrected_significant: bool
    expectancy_R_after_change: float
    ci_low_after_change: float
    ci_high_after_change: float
    auto_apply_eligible: bool


@dataclass(frozen=True)
class CandidateVariant:
    """A proposed parameter change with the outcomes it would have produced."""

    bundle: str
    regime: str
    parameter: str
    old_value: float
    proposed_value: float
    outcomes: list[TradeOutcome]
    p_value: float


class Tuner:
    """A14/C5 — objective is expectancy_R, never win rate.

    Only proposes when SPRT accepts H1 AND the bucket survives family-wise
    (Benjamini-Hochberg) correction. auto_apply is off unless settings.auto_tune_enabled.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def propose(self, variants: list[CandidateVariant]) -> list[TunerProposal]:
        if not variants:
            return []
        mask = benjamini_hochberg([v.p_value for v in variants], q=0.10)
        proposals: list[TunerProposal] = []
        for variant, significant in zip(variants, mask, strict=True):
            rs = [o.realized_R for o in variant.outcomes]
            if not rs:
                continue
            expectancy = sum(rs) / len(rs)
            sprt = SPRT(
                alpha=self._settings.sprt_alpha,
                beta=self._settings.sprt_beta,
                h0_expectancy=self._settings.expectancy_floor_R,
                h1_expectancy=self._settings.expectancy_floor_R + 0.2,
            )
            state = sprt.initial()
            for r in rs:
                state = sprt.update(state, r)
            ci_low, ci_high = bootstrap_R_interval(rs, seed=0)

            if state.decision != "accept_H1" or not significant:
                continue

            auto = self._settings.auto_tune_enabled and ci_low > 0
            proposals.append(
                TunerProposal(
                    bundle=variant.bundle,
                    regime=variant.regime,
                    parameter=variant.parameter,
                    old_value=variant.old_value,
                    proposed_value=variant.proposed_value,
                    sprt_state=state.decision,
                    family_corrected_significant=significant,
                    expectancy_R_after_change=expectancy,
                    ci_low_after_change=ci_low,
                    ci_high_after_change=ci_high,
                    auto_apply_eligible=auto,
                )
            )
        return proposals
