from __future__ import annotations

from dataclasses import dataclass

from plutus.db.models import AccumulationPosition
from plutus.shared.regime.detector import RegimeVerdict


@dataclass(frozen=True)
class ConversionOutcome:
    offer: bool
    reason: str


class BullReadyConverter:
    """Spec 08 §7 — the only path capital crosses domains, and it is voluntary.

    A conversion is OFFERED when the regime flips BULL with confirmed breadth AND a
    swing setup exists on the symbol. The converter NEVER mutates state on its own;
    the operator confirms. `auto_convert` is off by default (B16 constraint).

    `technicals` is treated as opaque: any truthy value means a swing setup formed.
    accumulation/ must not import swing/, so the swing signal type is not referenced.
    """

    def __init__(self, auto_convert: bool = False) -> None:
        self.auto_convert = auto_convert

    def evaluate(
        self,
        position: AccumulationPosition,
        regime: RegimeVerdict,
        technicals: object | None,
    ) -> ConversionOutcome:
        if regime.label != "BULL":
            return ConversionOutcome(offer=False, reason="regime is not BULL")
        if not regime.breadth_confirmed:
            return ConversionOutcome(offer=False, reason="BULL regime not breadth-confirmed")
        if not technicals:
            return ConversionOutcome(offer=False, reason="no swing setup on the symbol")
        return ConversionOutcome(
            offer=True,
            reason=f"bull-ready: confirmed BULL regime + swing setup on {position.symbol}",
        )
