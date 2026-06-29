from __future__ import annotations

from plutus.shared.smart_money.delivery import DeliveryTrendScore
from plutus.shared.smart_money.per_stock_score import FlowScore
from plutus.swing.scoring.flow_pillar import flow_pillar, flow_pillar_from_full


def _delivery(score: int) -> DeliveryTrendScore:
    return DeliveryTrendScore(
        score_0_15=score,
        delivery_pct_today=0.55,
        delivery_pct_20d_median=0.45,
        trend_slope=0.01,
    )


def test_delivery_flow_pillar_passthrough_bounded() -> None:
    assert flow_pillar(_delivery(0)).score == 0
    assert flow_pillar(_delivery(15)).score == 15
    assert flow_pillar(_delivery(8)).score == 8


def test_delivery_flow_pillar_clamped_above_max() -> None:
    # Defensive: should never exceed max_points even if upstream score is mis-bounded.
    out = flow_pillar(DeliveryTrendScore(50, 0.9, 0.4, 0.05))
    assert out.score == 15


def test_full_flow_constructor_caps_to_15() -> None:
    full = FlowScore(total_0_15=99, components={"delivery": 8, "bulk_block": 5, "mf": 2})
    out = flow_pillar_from_full(full)
    assert out.score == 15
    assert out.source == "full_flow"


def test_delivery_source_label() -> None:
    out = flow_pillar(_delivery(7))
    assert out.source == "delivery_only"
    assert out.components == {"delivery": 7}
