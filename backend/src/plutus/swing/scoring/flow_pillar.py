"""Per-stock smart-money flow pillar (0..15) for the v4 swing selection brain.

The full :class:`plutus.shared.smart_money.per_stock_score.PerStockFlow` composer
weighs delivery 0.50 / bulk_block 0.35 / MF 0.15 for the swing domain. The
scheduler today only has the delivery dataframe in scope on the watch path, so
this pillar is *delivery-only* at first: a thin wrapper that passes the
:class:`DeliveryTrendScore` (already 0..15) through to the composite.

When the bulk-block + MF providers are wired into the per-symbol loop the
``flow_pillar_from_full`` constructor can replace ``flow_pillar`` without
touching the call sites.

See ``SWING_SYSTEM_REVIEW.md`` sections 4.1 and 8 (item #2).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from plutus.shared.smart_money.delivery import DeliveryTrend, DeliveryTrendScore
from plutus.shared.smart_money.per_stock_score import FlowScore


@dataclass(frozen=True)
class FlowPillar:
    score: int  # 0..15
    components: dict[str, int]  # contributions of each sub-input (delivery only today)
    source: str  # "delivery_only" | "full_flow"


def flow_pillar(delivery: DeliveryTrendScore, *, max_points: int = 15) -> FlowPillar:
    """Delivery-only flow pillar.

    Delivery alone is the dominant swing input (50% of the full flow weight) and
    the India-specific edge the review calls out. Bulk-block + MF are TODOs.
    """
    raw = int(delivery.score_0_15)
    score = max(0, min(max_points, raw))
    return FlowPillar(
        score=score,
        components={"delivery": score},
        source="delivery_only",
    )


def flow_pillar_from_full(flow: FlowScore, *, max_points: int = 15) -> FlowPillar:
    """Forward-compatible constructor used once bulk_block + MF are wired.

    PerStockFlow.compose already caps at 15; we re-cap here for safety in case
    ``max_points`` ever diverges from the composer's internal cap.
    """
    score = max(0, min(max_points, int(flow.total_0_15)))
    return FlowPillar(score=score, components=dict(flow.components), source="full_flow")


def flow_score_from_history(delivery_df: pd.DataFrame | None) -> int:
    """0-15 flow score straight from a delivery-% history DataFrame (ascending by
    date, last row = most recent). 0 if there's not enough history yet — e.g. the
    daily delivery fetch job hasn't accumulated data for this symbol yet.

    Convenience entry point for callers that only care about the delivery-only
    flow score (not the full v4 pillar bundle) — the legacy composite paths.
    """
    if delivery_df is None or len(delivery_df) < 2:
        return 0
    trend = DeliveryTrend().compute(delivery_df, len(delivery_df) - 1)
    return flow_pillar(trend).score
