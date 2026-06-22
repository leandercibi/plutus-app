from __future__ import annotations

from dataclasses import dataclass, field

from plutus.accumulation.fundamentals.hard_avoid import (
    FundamentalsSnapshot,
    HardAvoid,
)
from plutus.config.settings import Settings
from plutus.db.models import AccumulationPosition

_EXITED_STATE = "EXITED"


@dataclass(frozen=True)
class ExitDecision:
    exit: bool
    reasons: list[str] = field(default_factory=list)
    new_state: str | None = None


class ThesisInvalidationExit:
    """B9 — re-runs HardAvoid on every weekly re-score. If a hard-avoid condition
    fires post-entry, the position exits even at a loss (no 'hold through anything').
    """

    def __init__(self, settings: Settings) -> None:
        self._hard_avoid = HardAvoid(settings)

    def evaluate(
        self,
        position: AccumulationPosition,
        latest_fundamentals: FundamentalsSnapshot,
    ) -> ExitDecision:
        result = self._hard_avoid.evaluate(latest_fundamentals)
        if result.avoid:
            position.state = _EXITED_STATE
            return ExitDecision(
                exit=True, reasons=result.reasons, new_state=_EXITED_STATE
            )
        return ExitDecision(exit=False, reasons=[], new_state=None)
