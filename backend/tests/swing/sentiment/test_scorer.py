from __future__ import annotations

from datetime import datetime

import pytest

from plutus.config.settings import Settings
from plutus.swing.sentiment.scorer import SentimentScorer, SentimentTiers
from plutus.swing.sentiment.types import Headline


def _hl(
    title: str,
    body: str = "",
    source: str = "src.com",
    entities: list[str] | None = None,
) -> Headline:
    return Headline(
        source=source,
        published_at=datetime(2024, 1, 1, 9, 0, 0),
        title=title,
        body=body,
        entities=entities if entities is not None else [],
    )


@pytest.fixture
def scorer() -> SentimentScorer:
    return SentimentScorer(Settings(_env_file=None))


def test_positive_headlines_produce_positive_score(scorer: SentimentScorer) -> None:
    headlines = [
        _hl("INFY reports record profit and strong upgrade", entities=["INFY"]),
        _hl("INFY wins major contract, beats estimates", entities=["INFY"]),
    ]
    result = scorer.score(headlines, "INFY")
    assert result.raw_score > 0
    assert result.score_0_5 > 0
    assert result.fired_keywords  # at least one keyword fired


def test_negative_headlines_produce_negative_raw_score(scorer: SentimentScorer) -> None:
    headlines = [
        _hl("INFY hit by fraud probe and downgrade", entities=["INFY"]),
    ]
    result = scorer.score(headlines, "INFY")
    assert result.raw_score < 0


def test_no_headlines_zero_score(scorer: SentimentScorer) -> None:
    result = scorer.score([], "INFY")
    assert result.raw_score == 0
    assert result.score_0_5 == 0
    assert result.headline_count == 0
    assert result.fired_keywords == []


def test_headline_count_tracks_input(scorer: SentimentScorer) -> None:
    headlines = [
        _hl("neutral news", entities=["INFY"]),
        _hl("more neutral", entities=["INFY"]),
    ]
    result = scorer.score(headlines, "INFY")
    assert result.headline_count == 2


@pytest.mark.hallmark
def test_score_capped_at_5_a8(scorer: SentimentScorer) -> None:
    # Many strongly-positive headlines must never push the pillar contribution above 5.
    headlines = [
        _hl(
            "INFY record profit upgrade beats estimates wins contract strong",
            entities=["INFY"],
        )
        for _ in range(50)
    ]
    result = scorer.score(headlines, "INFY")
    assert result.raw_score > 5  # uncapped diagnostic is large
    assert result.score_0_5 == 5  # contribution capped at exactly 5 (A8 weight cut)


def test_score_capped_at_zero_floor(scorer: SentimentScorer) -> None:
    # Strongly negative many headlines: capped contribution never goes below 0.
    headlines = [
        _hl("INFY fraud probe downgrade scandal loss default", entities=["INFY"]) for _ in range(50)
    ]
    result = scorer.score(headlines, "INFY")
    assert result.raw_score < 0
    assert result.score_0_5 == 0


def test_custom_tiers_injectable(scorer: SentimentScorer) -> None:
    tiers = SentimentTiers(
        positive_keywords={"moonshot": 3},
        negative_keywords={"crater": 4},
        structural_events={"rating_downgrade"},
    )
    custom = SentimentScorer(Settings(_env_file=None), tiers=tiers)
    pos = custom.score([_hl("INFY moonshot today", entities=["INFY"])], "INFY")
    assert "moonshot" in pos.fired_keywords
    assert pos.raw_score == 3
