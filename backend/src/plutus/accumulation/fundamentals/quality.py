from __future__ import annotations

# Quality pillar is out of 30 (spec 08 §2), split across three sub-factors.
QUALITY_MAX = 30
_ROCE_MAX = 14
_DE_MAX = 10
_FCF_MAX = 6

# Sub-factor ceilings used to scale raw fundamentals into points.
_ROCE_CEILING = 0.25  # ROCE at/above 25% earns full ROCE points
_DE_FULL = 0.0  # zero debt earns full D/E points
_DE_ZERO = 2.0  # D/E at/above 2.0 earns no D/E points
_FCF_CEILING = 0.20  # FCF margin at/above 20% earns full FCF points


class Quality:
    """Quality pillar (spec 08 §2): higher ROCE, lower D/E, positive FCF margin."""

    def score(self, roce: float, de: float, fcf_margin: float) -> int:
        roce_points = _scaled(roce, _ROCE_CEILING, _ROCE_MAX)
        de_points = _inverse_scaled(de, _DE_FULL, _DE_ZERO, _DE_MAX)
        fcf_points = _scaled(fcf_margin, _FCF_CEILING, _FCF_MAX)
        total = roce_points + de_points + fcf_points
        return max(0, min(int(round(total)), QUALITY_MAX))


def _scaled(value: float, ceiling: float, max_points: int) -> float:
    if ceiling <= 0.0:
        return 0.0
    fraction = min(max(value, 0.0) / ceiling, 1.0)
    return fraction * max_points


def _inverse_scaled(value: float, full_at: float, zero_at: float, max_points: int) -> float:
    """Full points at `full_at`, linearly down to 0 at `zero_at`."""
    if value <= full_at:
        return float(max_points)
    if value >= zero_at:
        return 0.0
    fraction = (zero_at - value) / (zero_at - full_at)
    return fraction * max_points
