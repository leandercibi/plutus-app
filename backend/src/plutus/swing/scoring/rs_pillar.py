"""Stock relative-strength pillar (0..15) for the v4 swing selection brain.

Wraps :class:`plutus.shared.rs.blend.RSBlend` and maps its blended
30/90/180-day vs-NIFTY relative return onto a bounded integer pillar.

Anchors (chosen to spread real swing leaders, not to win extreme tails):
  * blended >= +0.10  -> 15 pts (strong outperformer)
  * blended <= -0.10  -> 0  pts (laggard)
  * linear in between.

See ``SWING_SYSTEM_REVIEW.md`` sections 4.1 and 8 (item #1).
"""

from __future__ import annotations

from dataclasses import dataclass

from plutus.shared.rs.blend import RSBlendResult

_ANCHOR_HI = 0.10
_ANCHOR_LO = -0.10


@dataclass(frozen=True)
class RSPillar:
    score: int                 # 0..15
    blended: float             # raw blended relative return
    components: tuple[float, float, float]  # (rs_30, rs_90, rs_180)


def rs_pillar(blend: RSBlendResult, *, max_points: int = 15) -> RSPillar:
    """Map a blended RS reading to a 0..max_points pillar score (clipped)."""
    span = _ANCHOR_HI - _ANCHOR_LO
    fraction = (blend.blended - _ANCHOR_LO) / span
    clipped = max(0.0, min(1.0, fraction))
    score = int(round(clipped * float(max_points)))
    return RSPillar(
        score=score,
        blended=float(blend.blended),
        components=(float(blend.rs_30), float(blend.rs_90), float(blend.rs_180)),
    )
