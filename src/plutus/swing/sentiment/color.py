from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from plutus.swing.sentiment.scorer import SentimentScore
from plutus.swing.sentiment.types import Headline

# An LLM client is any callable prompt -> narrative string. The default is an
# offline stub so this module never performs network IO during tests.
LLMClient = Callable[[str], str]


def _default_client(prompt: str) -> str:
    return "Sentiment narrative unavailable (offline)."


@dataclass(frozen=True)
class SentimentColor:
    narrative: str


class SentimentColorist:
    """LLM-narration adapter. Output is display-only text (00_principles §4).

    The return value is `SentimentColor` (text only) and must never feed scoring.
    """

    def __init__(self, client: LLMClient | None = None) -> None:
        self._client = client if client is not None else _default_client

    def narrate(
        self, headlines: list[Headline], score: SentimentScore
    ) -> SentimentColor:
        prompt = self._build_prompt(headlines, score)
        narrative = self._client(prompt)
        return SentimentColor(narrative=narrative)

    def _build_prompt(self, headlines: list[Headline], score: SentimentScore) -> str:
        titles = "; ".join(hl.title for hl in headlines[:5])
        return (
            "Summarize the news sentiment in 2-3 neutral sentences for a dashboard "
            f"card. Headlines: {titles}. Fired keywords: {', '.join(score.fired_keywords)}."
        )
