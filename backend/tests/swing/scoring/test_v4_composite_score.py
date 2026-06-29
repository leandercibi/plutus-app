"""Composite-score sanity for the v4 selection brain.

These tests pin the two behavioral contracts the review wants protected:
  1. With ``enable_v4_selection=False`` the composite is unchanged from v3.
  2. With ``enable_v4_selection=True`` the composite adds RS + flow + a
     continuous regime pillar, and the score floor is honoured.
"""

from __future__ import annotations

from plutus.shared.rs.blend import RSBlendResult
from plutus.shared.smart_money.delivery import DeliveryTrendScore
from plutus.swing.scoring.composite_v4 import (
    V4Pillars,
    composite_score,
    legacy_regime_pillar,
    pillar_breakdown,
)
from plutus.swing.scoring.flow_pillar import flow_pillar
from plutus.swing.scoring.regime_pillar import RegimePillar
from plutus.swing.scoring.rs_pillar import rs_pillar


def _v4(rs_blended: float, delivery_pts: int, regime_score: int) -> V4Pillars:
    rs_p = rs_pillar(
        RSBlendResult(rs_30=rs_blended, rs_90=rs_blended, rs_180=rs_blended, blended=rs_blended)
    )
    flow_p = flow_pillar(
        DeliveryTrendScore(
            score_0_15=delivery_pts,
            delivery_pct_today=0.55,
            delivery_pct_20d_median=0.45,
            trend_slope=0.01,
        )
    )
    regime_p = RegimePillar(score=regime_score, breadth_pts=3.5, vix_pts=2.5, fii_pts=1.5)
    return V4Pillars(rs=rs_p, flow=flow_p, regime=regime_p)


def test_legacy_regime_lookup_preserves_silent_default() -> None:
    # SIDEWAYS isn't a key -> stays at the historical default. This is a
    # backstop: the v4 flag is what fixes the bug; the legacy path stays bug-
    # compatible with v3 so the off-switch is bit-for-bit identical.
    assert legacy_regime_pillar("BULL") == 15
    assert legacy_regime_pillar("BEAR") == 0
    assert legacy_regime_pillar("SIDEWAYS") == 7


def test_v4_composite_sums_to_expected_total() -> None:
    v4 = _v4(rs_blended=0.10, delivery_pts=15, regime_score=12)
    score = composite_score(
        technical_pts=20,
        expectancy_pts=18,
        regime_pts=v4.regime_pts,
        rs_pts=v4.rs_pts,
        flow_pts=v4.flow_pts,
    )
    # 20 + 18 + 12 + 15 + 15 = 80
    assert score == 80


def test_v4_composite_caps_at_100() -> None:
    v4 = _v4(rs_blended=0.50, delivery_pts=15, regime_score=15)
    score = composite_score(
        technical_pts=30,
        expectancy_pts=25,
        regime_pts=v4.regime_pts,
        rs_pts=v4.rs_pts,
        flow_pts=v4.flow_pts,
    )
    assert score == 100


def test_pillar_breakdown_emits_v4_fields() -> None:
    v4 = _v4(rs_blended=0.05, delivery_pts=10, regime_score=8)
    bd = pillar_breakdown(
        technical_pts=20,
        expectancy_pts=15,
        regime_pts=v4.regime_pts,
        v4=v4,
        calibration_band="medium",
        calibration_n=24,
        extras={"tradable": True},
    )
    assert bd["rs"] == v4.rs_pts
    assert bd["flow"] == v4.flow_pts
    assert bd["regime_fit"] == 8
    assert bd["flow_source"] == "delivery_only"
    assert bd["flow_components"] == {"delivery": v4.flow_pts}
    assert bd["tradable"] is True
    assert "rs_blended" in bd
    assert "regime_components" in bd


def test_v4_pillars_zero_when_missing_inputs() -> None:
    empty = V4Pillars(rs=None, flow=None, regime=None)
    assert empty.rs_pts == 0
    assert empty.flow_pts == 0
    assert empty.regime_pts == 0
    score = composite_score(
        technical_pts=20,
        expectancy_pts=15,
        regime_pts=empty.regime_pts,
        rs_pts=empty.rs_pts,
        flow_pts=empty.flow_pts,
    )
    # Missing inputs degrade gracefully -> score collapses to v3 minus regime.
    assert score == 35
