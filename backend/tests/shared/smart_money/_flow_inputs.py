from __future__ import annotations

from decimal import Decimal

from plutus.shared.smart_money.bulk_block import BulkBlockScore
from plutus.shared.smart_money.delivery import DeliveryTrendScore
from plutus.shared.smart_money.mf_accumulation import MFAccumulationVerdict


def delivery(score: int) -> DeliveryTrendScore:
    return DeliveryTrendScore(
        score_0_15=score,
        delivery_pct_today=0.5,
        delivery_pct_20d_median=0.4,
        trend_slope=0.01,
    )


def bb(score: int) -> BulkBlockScore:
    return BulkBlockScore(score_0_15=score, buyer_class="MF", net_value_inr=Decimal("10000000"))


def mf(verdict: str, confidence: float) -> MFAccumulationVerdict:
    return MFAccumulationVerdict(verdict=verdict, age_days=0, confidence_after_decay=confidence)
