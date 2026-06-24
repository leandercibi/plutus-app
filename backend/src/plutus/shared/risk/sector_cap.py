from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from plutus.config.settings import Settings
from plutus.shared.risk.types import OpenPosition


class _Proposable(Protocol):
    symbol: str
    sector: str


@dataclass(frozen=True)
class CapDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


class SectorCap:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def check(
        self,
        open_positions: list[OpenPosition],
        proposed: _Proposable,
        pool_value_inr: Decimal,
        proposed_value_inr: float | None = None,
    ) -> CapDecision:
        reasons: list[str] = []

        same_sector = [p for p in open_positions if p.sector == proposed.sector]
        projected_count = len(same_sector) + 1
        if projected_count > self._settings.sector_cap_count:
            reasons.append(
                f"sector {proposed.sector} count {projected_count} exceeds "
                f"cap {self._settings.sector_cap_count}"
            )

        if proposed_value_inr is not None and pool_value_inr > 0:
            existing_value = sum(
                p.position_value_inr
                for p in same_sector
                if p.position_value_inr is not None
            )
            projected_value = existing_value + proposed_value_inr
            exposure_pct = projected_value / float(pool_value_inr)
            if exposure_pct > self._settings.sector_cap_pct_of_pool:
                reasons.append(
                    f"sector {proposed.sector} exposure {exposure_pct:.1%} exceeds "
                    f"cap {self._settings.sector_cap_pct_of_pool:.1%}"
                )

        return CapDecision(allowed=not reasons, reasons=reasons)
