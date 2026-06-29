from __future__ import annotations

from dataclasses import dataclass

# Spec 08 §2 pillar weights (sum == 100).
QUALITY_WEIGHT = 30
GROWTH_WEIGHT = 25
VALUATION_WEIGHT = 30  # hard cap (A12)
RS_WEIGHT = 15

_RS_BLEND_CEILING = 0.20  # blended RS at/above 20% earns full RS points


@dataclass(frozen=True)
class AccumulationPillars:
    quality: int
    growth: int
    valuation: int
    relative_strength: int
    total: int


def rs_points(blended_rs: float) -> int:
    """Map the RS blend into the 0..RS_WEIGHT pillar contribution."""
    fraction = min(max(blended_rs, 0.0) / _RS_BLEND_CEILING, 1.0)
    return int(round(fraction * RS_WEIGHT))


def compose_pillars(
    quality: int, growth: int, valuation: int, blended_rs: float
) -> AccumulationPillars:
    """Compose the four accumulation pillars into a 0..100 total.

    Inputs are pre-scored sub-pillars (quality 0..30, growth 0..25,
    valuation 0..30 hard-capped). Each is clamped to its weight before summing.
    """
    q = _clamp(quality, QUALITY_WEIGHT)
    g = _clamp(growth, GROWTH_WEIGHT)
    v = _clamp(valuation, VALUATION_WEIGHT)
    rs = rs_points(blended_rs)
    total = q + g + v + rs
    return AccumulationPillars(
        quality=q,
        growth=g,
        valuation=v,
        relative_strength=rs,
        total=total,
    )


def _clamp(value: int, ceiling: int) -> int:
    return max(0, min(value, ceiling))
