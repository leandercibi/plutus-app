from __future__ import annotations

from plutus.shared.rs.blend import RSBlendResult
from plutus.swing.scoring.rs_pillar import rs_pillar


def _blend(b: float) -> RSBlendResult:
    return RSBlendResult(rs_30=b, rs_90=b, rs_180=b, blended=b)


def test_rs_pillar_is_bounded_0_to_15() -> None:
    for raw in (-1.0, -0.05, 0.0, 0.05, 1.0):
        out = rs_pillar(_blend(raw))
        assert 0 <= out.score <= 15


def test_strong_outperformer_scores_higher_than_laggard() -> None:
    strong = rs_pillar(_blend(0.20))
    weak = rs_pillar(_blend(-0.20))
    assert strong.score > weak.score


def test_anchor_clipping() -> None:
    # Saturated above +10% relative -> exact max
    assert rs_pillar(_blend(0.25)).score == 15
    # Saturated below -10% relative -> exact min
    assert rs_pillar(_blend(-0.25)).score == 0


def test_neutral_rs_sits_near_mid() -> None:
    mid = rs_pillar(_blend(0.0))
    assert 6 <= mid.score <= 9
