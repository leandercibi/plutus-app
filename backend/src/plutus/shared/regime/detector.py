from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from plutus.config.settings import Settings


@dataclass(frozen=True)
class RegimeInputs:
    nifty_close: Decimal
    nifty_50dma: Decimal
    nifty_200dma: Decimal
    pct_above_50dma: float
    pct_above_200dma: float
    advance_decline: float
    india_vix: float
    fii_flow_5d_sum_inr: Decimal
    dii_flow_5d_sum_inr: Decimal
    # prior breadth reading used to judge the 5d trend for breadth_confirmed
    pct_above_50dma_5d_ago: float = 0.0


@dataclass(frozen=True)
class RegimeVerdict:
    label: Literal["BULL", "BEAR", "SIDEWAYS"]
    confidence: Literal["low", "medium", "high"]
    reasons: list[str] = field(default_factory=list)
    breadth_confirmed: bool = False


def _confidence_from_count(n_satisfied: int) -> Literal["low", "medium", "high"]:
    if n_satisfied >= 3:
        return "high"
    if n_satisfied == 2:
        return "medium"
    return "low"


class RegimeDetector:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def classify(self, inputs: RegimeInputs) -> RegimeVerdict:
        bull_rules = self._bull_rules(inputs)
        bear_rules = self._bear_rules(inputs)
        bull_count = sum(1 for _, ok in bull_rules if ok)
        bear_count = sum(1 for _, ok in bear_rules if ok)

        if all(ok for _, ok in bull_rules):
            label: Literal["BULL", "BEAR", "SIDEWAYS"] = "BULL"
            reasons = [reason for reason, ok in bull_rules if ok]
            confidence = _confidence_from_count(bull_count)
            breadth = inputs.pct_above_50dma >= inputs.pct_above_50dma_5d_ago
        elif all(ok for _, ok in bear_rules):
            label = "BEAR"
            reasons = [reason for reason, ok in bear_rules if ok]
            confidence = _confidence_from_count(bear_count)
            breadth = inputs.pct_above_50dma <= inputs.pct_above_50dma_5d_ago
        else:
            label = "SIDEWAYS"
            reasons = ["no full bull or bear condition set satisfied"]
            confidence = "low"
            breadth = False

        return RegimeVerdict(
            label=label,
            confidence=confidence,
            reasons=reasons,
            breadth_confirmed=breadth,
        )

    def _bull_rules(self, inputs: RegimeInputs) -> list[tuple[str, bool]]:
        s = self._settings
        return [
            ("nifty above 200DMA", inputs.nifty_close > inputs.nifty_200dma),
            ("breadth >55% above 50DMA", inputs.pct_above_50dma > 0.55),
            (f"vix below {s.vix_bull_max}", inputs.india_vix < s.vix_bull_max),
            ("5d FII net positive", inputs.fii_flow_5d_sum_inr > 0),
        ]

    def _bear_rules(self, inputs: RegimeInputs) -> list[tuple[str, bool]]:
        s = self._settings
        return [
            ("nifty below 50DMA", inputs.nifty_close < inputs.nifty_50dma),
            ("nifty below 200DMA", inputs.nifty_close < inputs.nifty_200dma),
            ("breadth <30% above 200DMA", inputs.pct_above_200dma < 0.30),
            (f"vix above {s.vix_bear_min}", inputs.india_vix > s.vix_bear_min),
        ]
