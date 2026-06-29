from __future__ import annotations

from dataclasses import dataclass, field

from plutus.accumulation.fundamentals.hard_avoid import (
    FundamentalsSnapshot,
    HardAvoid,
)
from plutus.config.settings import Settings
from plutus.db.models import AccumulationPosition

# A13 — a quality pillar drop beyond this many points between tranches fails the
# pre-averaging-down thesis re-check.
_QUALITY_DROP_LIMIT = 10
_PAUSED_STATE = "PAUSED"


@dataclass(frozen=True)
class RevalidationOutcome:
    ok: bool
    reasons: list[str] = field(default_factory=list)


class TrancheRevalidator:
    """A13 — before any tranche after the first, the thesis is re-verified.

    On failure the position transitions to PAUSED and no further tranches deploy
    until the operator manually un-pauses.
    """

    def __init__(self, settings: Settings) -> None:
        self._hard_avoid = HardAvoid(settings)

    def revalidate(
        self,
        position: AccumulationPosition,
        latest_fundamentals: FundamentalsSnapshot,
        prior_quality_score: int,
        current_quality_score: int,
    ) -> RevalidationOutcome:
        reasons: list[str] = []

        hard_avoid_result = self._hard_avoid.evaluate(latest_fundamentals)
        if hard_avoid_result.avoid:
            reasons.extend(hard_avoid_result.reasons)

        quality_drop = prior_quality_score - current_quality_score
        if quality_drop > _QUALITY_DROP_LIMIT:
            reasons.append(
                f"quality pillar dropped {quality_drop} points "
                f"(> {_QUALITY_DROP_LIMIT}) since last tranche"
            )

        if reasons:
            position.state = _PAUSED_STATE
            return RevalidationOutcome(ok=False, reasons=reasons)
        return RevalidationOutcome(ok=True, reasons=[])
