from __future__ import annotations

from dataclasses import dataclass, field

from plutus.config.settings import Settings

# Thresholds fixed by spec 08 §3.3.
_EPS_COLLAPSE_THRESHOLD = -0.50  # > 50% YoY drop
_PROMOTER_PLEDGE_THRESHOLD_PP = 10.0  # > 10pp increase in a quarter


@dataclass(frozen=True)
class FundamentalsSnapshot:
    de: float
    is_financial: bool
    last_eps_yoy_change: float  # fractional, e.g. -0.60 == -60% YoY
    improving_guidance: bool
    going_concern_flag: bool
    promoter_pledge_increase_pp: float  # percentage points, last quarter
    roce: float
    fcf_margin: float
    pe_ttm: float


@dataclass(frozen=True)
class HardAvoidResult:
    avoid: bool
    reasons: list[str] = field(default_factory=list)


class HardAvoid:
    """Spec 08 §3.3 — fundamentals-driven hard-avoid triggers (A12/B9)."""

    def __init__(self, settings: Settings) -> None:
        self._de_max = settings.accumulation_de_max

    def evaluate(self, fundamentals: FundamentalsSnapshot) -> HardAvoidResult:
        reasons: list[str] = []

        if not fundamentals.is_financial and fundamentals.de > self._de_max:
            reasons.append(
                f"D/E {fundamentals.de:.2f} exceeds max {self._de_max:.2f} (non-financial)"
            )

        if (
            fundamentals.last_eps_yoy_change < _EPS_COLLAPSE_THRESHOLD
            and not fundamentals.improving_guidance
        ):
            reasons.append(
                f"EPS collapse {fundamentals.last_eps_yoy_change:.0%} YoY with no improving guidance"
            )

        if fundamentals.going_concern_flag:
            reasons.append("going concern audit flag")

        if fundamentals.promoter_pledge_increase_pp > _PROMOTER_PLEDGE_THRESHOLD_PP:
            reasons.append(
                f"promoter pledge increase {fundamentals.promoter_pledge_increase_pp:.1f}pp "
                f"exceeds {_PROMOTER_PLEDGE_THRESHOLD_PP:.0f}pp"
            )

        return HardAvoidResult(avoid=len(reasons) > 0, reasons=reasons)
