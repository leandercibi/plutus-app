from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from plutus.shared.smart_money.bulk_block import BulkBlockScore
from plutus.shared.smart_money.delivery import DeliveryTrendScore
from plutus.shared.smart_money.mf_accumulation import MFAccumulationVerdict

Domain = Literal["swing", "accumulation"]

# Domain weights (domain-fixed ratios; sum to 1.0 within each domain).
_WEIGHTS: dict[Domain, dict[str, float]] = {
    "swing": {"delivery": 0.50, "bulk_block": 0.35, "mf": 0.15},
    "accumulation": {"delivery": 0.35, "bulk_block": 0.20, "mf": 0.45},
}

# MF verdict -> base score before age-decay.
_MF_BASE: dict[str, int] = {"ACCUMULATING": 15, "NEUTRAL": 7, "DISTRIBUTING": 0}

_MAX_SCORE = 15


@dataclass(frozen=True)
class FlowScore:
    total_0_15: int
    components: dict[str, int]


class PerStockFlow:
    """Single composer used by both swing and accumulation pillars (spec 09 §9).
    The MF component is scaled by its confidence_after_decay (A7)."""

    def compose(
        self,
        delivery: DeliveryTrendScore,
        bb: BulkBlockScore,
        mf: MFAccumulationVerdict,
        domain: Domain,
    ) -> FlowScore:
        weights = _WEIGHTS[domain]
        mf_effective = _MF_BASE[mf.verdict] * mf.confidence_after_decay

        delivery_pts = int(round(delivery.score_0_15 * weights["delivery"]))
        bulk_pts = int(round(bb.score_0_15 * weights["bulk_block"]))
        mf_pts = int(round(mf_effective * weights["mf"]))

        components = {"delivery": delivery_pts, "bulk_block": bulk_pts, "mf": mf_pts}
        total = min(_MAX_SCORE, delivery_pts + bulk_pts + mf_pts)
        return FlowScore(total_0_15=total, components=components)
