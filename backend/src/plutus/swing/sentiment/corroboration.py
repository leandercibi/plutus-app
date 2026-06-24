from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from plutus.config.settings import Settings
from plutus.swing.sentiment.entity_resolver import EntityResolver
from plutus.swing.sentiment.types import Headline

HardKillReason = Literal[
    "two_entity_headlines",
    "headline_plus_pricevol",
    "structural_event",
    "uncorroborated",
]

_STRUCTURAL_PREFIX = "structural_event:"
_PRICEVOL_VOLUME_MULT = 1.5
_GAP_DOWN_PCT = 0.0  # any open below prior close counts as a gap-down here
_MAX_PENALTY = 3


@dataclass(frozen=True)
class HardKillVerdict:
    fires: bool
    reason: HardKillReason
    penalty_only: int


def _source_domain(source: str) -> str:
    return source.lower().split("/")[0].strip()


class HardKillEvaluator:
    def __init__(
        self, settings: Settings, resolver: EntityResolver | None = None
    ) -> None:
        self._settings = settings
        self._resolver = resolver if resolver is not None else EntityResolver()

    def evaluate(
        self, headlines: list[Headline], today_candles: pd.DataFrame, symbol: str
    ) -> HardKillVerdict:
        high_conf = [
            hl
            for hl in headlines
            if self._resolver.resolve(hl, symbol).confidence == "high"
        ]

        # (3) structural event class — provider-verified, entity-matched
        if self._has_structural_event(high_conf):
            return HardKillVerdict(True, "structural_event", 0)

        # (1) >=2 independent (different source domain) high-confidence headlines
        domains = {_source_domain(hl.source) for hl in high_conf}
        if len(high_conf) >= 2 and len(domains) >= 2:
            return HardKillVerdict(True, "two_entity_headlines", 0)

        # (2) >=1 high-confidence headline AND price gap-down on high delivery volume
        if high_conf and self._gap_down_on_volume(today_candles):
            return HardKillVerdict(True, "headline_plus_pricevol", 0)

        # otherwise: graded penalty, no kill
        penalty = self._graded_penalty(headlines, symbol)
        return HardKillVerdict(False, "uncorroborated", penalty)

    def _has_structural_event(self, high_conf: list[Headline]) -> bool:
        for hl in high_conf:
            if _STRUCTURAL_PREFIX in hl.body:
                event = hl.body.split(_STRUCTURAL_PREFIX, 1)[1].strip()
                if event in self._structural_events():
                    return True
        return False

    def _structural_events(self) -> set[str]:
        return {"rating_downgrade", "exchange_filing_adverse", "regulator_action"}

    def _gap_down_on_volume(self, candles: pd.DataFrame) -> bool:
        if len(candles) < 2 or "delivery_adjusted_volume" not in candles.columns:
            return False
        prior_close = float(candles["close"].iloc[-2])
        today_open = float(candles["open"].iloc[-1])
        gap_down = today_open < prior_close * (1.0 - _GAP_DOWN_PCT)
        prior_vol = float(candles["delivery_adjusted_volume"].iloc[-2])
        today_vol = float(candles["delivery_adjusted_volume"].iloc[-1])
        high_vol = prior_vol > 0 and today_vol > prior_vol * _PRICEVOL_VOLUME_MULT
        return gap_down and high_vol

    def _graded_penalty(self, headlines: list[Headline], symbol: str) -> int:
        penalty = 0
        for hl in headlines:
            conf = self._resolver.resolve(hl, symbol).confidence
            if conf in ("high", "medium"):
                penalty += 1
            elif conf == "low":
                penalty += 0
        return min(penalty, _MAX_PENALTY)
