"""Composite score assembly for the v4 swing selection brain.

Glues the three new pillars (RS, flow, continuous regime) onto the existing
technical + expectancy composite. Centralised here so the watch_screen path and
the bundle-signal path in :mod:`plutus.scheduler.jobs` use *exactly* the same
formula - if they diverge the score becomes meaningless across cohorts.

See ``SWING_SYSTEM_REVIEW.md`` section 8 (items #1 through #3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from plutus.shared.rs.blend import RSBlend, RSBlendResult
from plutus.config.settings import Settings
from plutus.shared.regime.detector import RegimeInputs
from plutus.shared.smart_money.delivery import DeliveryTrend
from plutus.swing.scoring.flow_pillar import FlowPillar, flow_pillar
from plutus.swing.scoring.regime_pillar import RegimePillar, regime_pillar_continuous
from plutus.swing.scoring.rs_pillar import RSPillar, rs_pillar

_LEGACY_REGIME_PILLAR: dict[str, int] = {
    "BULL": 15,
    "SOFT_BULL": 10,
    "NEUTRAL": 7,
    "SOFT_BEAR": 3,
    "BEAR": 0,
}


@dataclass(frozen=True)
class V4Pillars:
    """Per-symbol bundle of the three new pillars (already capped to 0..15)."""

    rs: RSPillar | None
    flow: FlowPillar | None
    regime: RegimePillar | None

    @property
    def rs_pts(self) -> int:
        return self.rs.score if self.rs is not None else 0

    @property
    def flow_pts(self) -> int:
        return self.flow.score if self.flow is not None else 0

    @property
    def regime_pts(self) -> int:
        return self.regime.score if self.regime is not None else 0


def compute_v4_pillars(
    *,
    candles: pd.DataFrame,
    delivery_df: pd.DataFrame | None,
    nifty_df: pd.DataFrame | None,
    regime_inputs: RegimeInputs,
    rs_engine: RSBlend,
    settings: Settings,
) -> V4Pillars:
    """Compute the three v4 pillars for a single symbol.

    Any pillar whose inputs are insufficient becomes ``None`` and contributes
    0 points downstream.
    """

    rs: RSPillar | None = None
    if nifty_df is not None and len(nifty_df) >= 181 and len(candles) >= 181:
        try:
            blend: RSBlendResult = rs_engine.compute(candles, nifty_df)
            rs = rs_pillar(blend)
        except Exception:
            rs = None

    flow: FlowPillar | None = None
    if delivery_df is not None and len(delivery_df) > 0:
        try:
            today_idx = len(delivery_df) - 1
            delivery_score = DeliveryTrend().compute(delivery_df, today_idx)
            flow = flow_pillar(delivery_score)
        except Exception:
            flow = None

    regime: RegimePillar | None = None
    try:
        regime = regime_pillar_continuous(regime_inputs, settings)
    except Exception:
        regime = None

    return V4Pillars(rs=rs, flow=flow, regime=regime)


def legacy_regime_pillar(regime_label: str) -> int:
    """Bit-for-bit reproduction of the old bucket lookup.

    Kept for the ``enable_v4_selection=False`` codepath so v3 behaviour is
    preserved exactly. Note the silent ``SIDEWAYS -> 7`` default the review
    flags - it is *intentional* here to preserve the legacy path; the new
    continuous pillar replaces it under the flag.
    """
    return _LEGACY_REGIME_PILLAR.get(regime_label, 7)


def composite_score(
    *,
    technical_pts: int,
    expectancy_pts: int,
    regime_pts: int,
    rs_pts: int,
    flow_pts: int,
) -> int:
    """Sum the five-pillar composite.

    Capped at 100 by construction (30 + 25 + 15 + 15 + 15).
    """
    return technical_pts + expectancy_pts + regime_pts + rs_pts + flow_pts


def pillar_breakdown(
    *,
    technical_pts: int,
    expectancy_pts: int,
    regime_pts: int,
    v4: V4Pillars,
    calibration_band: str,
    calibration_n: int,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the ``SwingSignal.pillar_breakdown_json`` payload with v4 fields."""
    breakdown: dict[str, Any] = {
        "technical": technical_pts,
        "expectancy": expectancy_pts,
        "flow": v4.flow_pts,
        "sentiment": 0,
        "regime_fit": regime_pts,
        "fundamentals": 0,
        "rs": v4.rs_pts,
        "calibration_band": calibration_band,
        "calibration_n": calibration_n,
    }
    if v4.rs is not None:
        breakdown["rs_blended"] = round(v4.rs.blended, 4)
    if v4.flow is not None:
        breakdown["flow_source"] = v4.flow.source
        breakdown["flow_components"] = v4.flow.components
    if v4.regime is not None:
        breakdown["regime_components"] = {
            "breadth_pts": round(v4.regime.breadth_pts, 2),
            "vix_pts": round(v4.regime.vix_pts, 2),
            "fii_pts": round(v4.regime.fii_pts, 2),
        }
    if extras:
        breakdown.update(extras)
    return breakdown
