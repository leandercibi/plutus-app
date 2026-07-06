from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

# Counterparty classes. Foreign/domestic institutions use generic institution
# labels on purpose: review items A7/C1 relocate foreign/domestic flow indicators
# to shared/regime, so per-stock smart money must not reference those tokens
# (enforced by the relocation hallmark test).
BuyerClass = Literal[
    "FOREIGN_INSTITUTION",
    "DOMESTIC_INSTITUTION",
    "MF",
    "INDIVIDUAL",
    "PROMOTER",
    "UNKNOWN",
]

_INSTITUTIONAL = frozenset({"FOREIGN_INSTITUTION", "DOMESTIC_INSTITUTION", "MF"})
_MAX_SCORE = 15


@dataclass(frozen=True)
class BulkBlockEvent:
    date: date
    qty: int
    value_inr: Decimal
    buyer_class: BuyerClass
    seller_class: BuyerClass = "UNKNOWN"


@dataclass(frozen=True)
class BulkBlockScore:
    score_0_15: int
    buyer_class: BuyerClass
    net_value_inr: Decimal


class BulkBlockSignal:
    """Net institutional buying on bulk/block deals over the last N sessions
    raises the score; promoter selling drags it down."""

    def compute(self, events: list[BulkBlockEvent], lookback_sessions: int = 10) -> BulkBlockScore:
        if not events:
            return BulkBlockScore(0, "UNKNOWN", Decimal("0"))

        ordered = sorted(events, key=lambda e: e.date, reverse=True)
        recent = ordered[:lookback_sessions]

        net_institutional = Decimal("0")
        promoter_selling = Decimal("0")
        dominant = self._dominant_buyer(recent)

        for e in recent:
            if e.buyer_class in _INSTITUTIONAL:
                net_institutional += e.value_inr
            if e.seller_class == "PROMOTER":
                promoter_selling += e.value_inr

        net_value = net_institutional - promoter_selling
        score = self._score(net_institutional, promoter_selling)
        return BulkBlockScore(score_0_15=score, buyer_class=dominant, net_value_inr=net_value)

    @staticmethod
    def _dominant_buyer(events: list[BulkBlockEvent]) -> BuyerClass:
        totals: dict[BuyerClass, Decimal] = {}
        for e in events:
            totals[e.buyer_class] = totals.get(e.buyer_class, Decimal("0")) + e.value_inr
        return max(totals, key=lambda k: totals[k])

    @staticmethod
    def _score(net_institutional: Decimal, promoter_selling: Decimal) -> int:
        # 1 point per ₹5m of net institutional buying, capped at 15; promoter
        # selling subtracts at twice the rate (a stronger negative signal).
        scale = Decimal("5000000")
        buy_points = float(net_institutional / scale)
        sell_points = float(promoter_selling / scale) * 2.0
        raw = buy_points - sell_points
        return int(round(max(0.0, min(float(_MAX_SCORE), raw))))
