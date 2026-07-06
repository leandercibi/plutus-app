"""Continuous regime pillar (0..15) for the v4 swing selection brain.

Replaces the silent five-bucket lookup
``{BULL:15, SOFT_BULL:10, NEUTRAL:7, SOFT_BEAR:3, BEAR:0}.get(label, 7)`` that
mapped every ``SIDEWAYS`` signal to a flat 7 (defaulted because ``SIDEWAYS`` was
never a key). The continuous variant uses the macro inputs the
:class:`RegimeDetector` already consumes:

  * breadth %-above-50DMA  -> 0..7 pts  (linear in [0.30, 0.70])
  * India VIX (inverted)   -> 0..5 pts  (linear in [vix_bear_min, vix_bull_max])
  * FII 5-day flow sign    -> 0..3 pts  (tanh-clipped on rupee flow)

The pillar is *market-wide* by design - cross-sectional spread inside a single
run comes from the RS + flow pillars, not from this one. The win here is
restoring graded regime resolution between runs (e.g. SIDEWAYS-with-improving-
breadth scores higher than SIDEWAYS-with-collapsing-breadth).

See ``SWING_SYSTEM_REVIEW.md`` sections 2.2 and 8 (item #3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from plutus.config.settings import Settings
from plutus.shared.regime.detector import RegimeInputs

_BREADTH_LO = 0.30
_BREADTH_HI = 0.70
_BREADTH_MAX_PTS = 7.0
_VIX_MAX_PTS = 5.0
_FII_MAX_PTS = 3.0
# FII 5d-cumulative scale: 1000 cr ~ saturated positive. Tuned to typical NSE
# foreign-flow magnitudes; tanh keeps both tails bounded without thresholds.
_FII_SCALE_INR = Decimal("10000000000")  # 1,000 crore

_TOTAL_MAX = int(_BREADTH_MAX_PTS + _VIX_MAX_PTS + _FII_MAX_PTS)  # 15


@dataclass(frozen=True)
class RegimePillar:
    score: int  # 0..15
    breadth_pts: float
    vix_pts: float
    fii_pts: float


def _clip_unit(x: float) -> float:
    return max(0.0, min(1.0, x))


def regime_pillar_continuous(
    inputs: RegimeInputs, settings: Settings, *, max_points: int = _TOTAL_MAX
) -> RegimePillar:
    breadth_frac = _clip_unit((inputs.pct_above_50dma - _BREADTH_LO) / (_BREADTH_HI - _BREADTH_LO))
    breadth_pts = breadth_frac * _BREADTH_MAX_PTS

    vix_lo = float(settings.vix_bull_max)
    vix_hi = float(settings.vix_bear_min)
    if vix_hi <= vix_lo:
        vix_frac = 0.5
    else:
        vix_frac = _clip_unit((vix_hi - inputs.india_vix) / (vix_hi - vix_lo))
    vix_pts = vix_frac * _VIX_MAX_PTS

    fii_norm = float(inputs.fii_flow_5d_sum_inr / _FII_SCALE_INR)
    fii_signed = math.tanh(fii_norm)
    fii_pts = (fii_signed + 1.0) / 2.0 * _FII_MAX_PTS

    raw = breadth_pts + vix_pts + fii_pts
    score = int(round(min(float(max_points), max(0.0, raw))))
    return RegimePillar(
        score=score,
        breadth_pts=breadth_pts,
        vix_pts=vix_pts,
        fii_pts=fii_pts,
    )
