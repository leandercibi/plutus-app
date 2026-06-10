# tests/test_scoring/test_pillar_sentiment.py
import pytest
from plutus.agents.scoring import sentiment_pillar


def test_positive_no_material_scores_high():
    score, _ = sentiment_pillar(
        news={"sentiment_score": 4.0, "sentiment_label": "positive",
              "is_material_event": False, "material_event_type": None},
    )
    assert score >= 70


def test_negative_material_zeros_pillar():
    score, hard = sentiment_pillar(
        news={"sentiment_score": -3.0, "sentiment_label": "negative",
              "is_material_event": True, "material_event_type": "regulatory"},
    )
    assert score == 0
    assert "material_negative_event" in hard


def test_positive_material_capped_below_max():
    score, _ = sentiment_pillar(
        news={"sentiment_score": 4.5, "sentiment_label": "positive",
              "is_material_event": True, "material_event_type": "earnings"},
    )
    assert 70 <= score <= 90  # capped at 85


def test_no_news_returns_neutral():
    score, _ = sentiment_pillar(
        news={"sentiment_score": 0, "sentiment_label": "neutral",
              "is_material_event": False, "material_event_type": None}
    )
    assert 45 <= score <= 55


def test_returns_0_100_range():
    for raw in [-5, -2.5, 0, 2.5, 5]:
        score, _ = sentiment_pillar(
            news={"sentiment_score": raw, "sentiment_label": "neutral",
                  "is_material_event": False}
        )
        assert 0 <= score <= 100, f"score {score} out of range for raw={raw}"
