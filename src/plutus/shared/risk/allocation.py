from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from plutus.config.settings import Settings
from plutus.shared.regime.detector import RegimeVerdict

_DESIRED_SWING_PCT = {"BULL": 0.7, "SIDEWAYS": 0.5, "BEAR": 0.3}


@dataclass(frozen=True)
class AllocationPlan:
    committed_swing: Decimal
    committed_accumulation: Decimal
    uncommitted: Decimal
    target_swing: Decimal
    target_accumulation: Decimal


class Allocation:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def desired_swing_pct(self, regime: RegimeVerdict) -> float:
        return _DESIRED_SWING_PCT[regime.label]

    def reallocate_uncommitted(
        self,
        total_capital: Decimal,
        committed_swing: Decimal,
        committed_accumulation: Decimal,
        regime: RegimeVerdict,
    ) -> AllocationPlan:
        uncommitted = total_capital - committed_swing - committed_accumulation
        desired_pct = Decimal(str(self.desired_swing_pct(regime)))
        desired_swing_total = total_capital * desired_pct

        # uncommitted pool tilts toward the regime swing target, but committed capital
        # on either side is never reduced (no force-migration).
        extra_swing = desired_swing_total - committed_swing
        if extra_swing < 0:
            extra_swing = Decimal("0")
        if extra_swing > uncommitted:
            extra_swing = uncommitted

        target_swing = committed_swing + extra_swing
        target_accumulation = committed_accumulation + (uncommitted - extra_swing)

        return AllocationPlan(
            committed_swing=committed_swing,
            committed_accumulation=committed_accumulation,
            uncommitted=uncommitted,
            target_swing=target_swing,
            target_accumulation=target_accumulation,
        )
