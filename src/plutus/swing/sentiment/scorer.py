from __future__ import annotations

from dataclasses import dataclass, field

from plutus.config.settings import Settings
from plutus.swing.sentiment.types import Headline

# Pillar contribution ceiling: 0..5 (A8 weight cut). Tied to the pillar weight
# (5% of a 100-point total). Derived from settings, not a free magic number.
_SCORE_SCALE = 4  # raw points per pillar point when mapping raw -> capped


@dataclass(frozen=True)
class SentimentTiers:
    positive_keywords: dict[str, int]
    negative_keywords: dict[str, int]
    structural_events: set[str]


_DEFAULT_TIERS = SentimentTiers(
    positive_keywords={
        "profit": 1,
        "record": 1,
        "upgrade": 2,
        "beats": 1,
        "estimates": 1,
        "wins": 1,
        "contract": 1,
        "strong": 1,
        "moonshot": 0,  # placeholder; overridden by custom tiers in tests
    },
    negative_keywords={
        "fraud": 3,
        "probe": 2,
        "downgrade": 2,
        "scandal": 3,
        "loss": 1,
        "default": 2,
    },
    structural_events={
        "rating_downgrade",
        "exchange_filing_adverse",
        "regulator_action",
    },
)


@dataclass(frozen=True)
class SentimentScore:
    score_0_5: int
    raw_score: int
    headline_count: int
    fired_keywords: list[str] = field(default_factory=list)


class SentimentScorer:
    def __init__(self, settings: Settings, tiers: SentimentTiers | None = None) -> None:
        self._settings = settings
        self._tiers = tiers if tiers is not None else _DEFAULT_TIERS
        # cap in pillar points: 5% of 100 -> 5
        self._cap = int(round(settings.sentiment_pillar_weight * 100))

    def score(self, headlines: list[Headline], symbol: str) -> SentimentScore:
        raw = 0
        fired: list[str] = []
        for hl in headlines:
            text = f"{hl.title} {hl.body}".lower()
            for kw, weight in self._tiers.positive_keywords.items():
                if weight and kw in text:
                    raw += weight
                    fired.append(kw)
            for kw, weight in self._tiers.negative_keywords.items():
                if weight and kw in text:
                    raw -= weight
                    fired.append(kw)

        capped = self._cap_contribution(raw)
        return SentimentScore(
            score_0_5=capped,
            raw_score=raw,
            headline_count=len(headlines),
            fired_keywords=fired,
        )

    def _cap_contribution(self, raw: int) -> int:
        if raw <= 0:
            return 0
        scaled = raw // _SCORE_SCALE + (1 if raw % _SCORE_SCALE else 0)
        return min(scaled, self._cap)
