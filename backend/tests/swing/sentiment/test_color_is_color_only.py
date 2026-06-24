from __future__ import annotations

import ast
from dataclasses import fields
from datetime import datetime
from pathlib import Path

import pytest

from plutus.config.settings import Settings
from plutus.swing.sentiment.color import SentimentColor, SentimentColorist
from plutus.swing.sentiment.scorer import SentimentScorer
from plutus.swing.sentiment.types import Headline

_SCORING_DIR = Path("src/plutus/swing/scoring")


def _hl(title: str) -> Headline:
    return Headline(
        source="src.com",
        published_at=datetime(2024, 1, 1, 9, 0, 0),
        title=title,
        body="",
        entities=["INFY"],
    )


@pytest.mark.hallmark
def test_sentiment_color_has_only_text_field() -> None:
    # SentimentColor must carry text only, no numeric fields that could feed scoring.
    field_types = {f.name: f.type for f in fields(SentimentColor)}
    assert set(field_types) == {"narrative"}
    sample = SentimentColor(narrative="A neutral, descriptive sentence.")
    assert isinstance(sample.narrative, str)
    # no numeric attribute may exist on the color object
    for value in vars(sample).values():
        assert not isinstance(value, (int, float))


@pytest.mark.hallmark
def test_narrate_returns_color_only_offline() -> None:
    colorist = SentimentColorist(
        client=lambda prompt: "Markets reacted calmly to the news."
    )
    scorer = SentimentScorer(Settings(_env_file=None))
    score = scorer.score([_hl("INFY steady update")], "INFY")
    result = colorist.narrate([_hl("INFY steady update")], score)
    assert isinstance(result, SentimentColor)
    assert isinstance(result.narrative, str)
    assert result.narrative  # non-empty


@pytest.mark.hallmark
def test_no_scoring_module_imports_color() -> None:
    # AST walk over swing/scoring/: no file may import swing/sentiment/color.py
    offenders: list[str] = []
    for py in _SCORING_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                if "sentiment.color" in m or m.endswith(".color"):
                    offenders.append(f"{py.name}: {m}")
    assert offenders == [], f"scoring modules import color: {offenders}"
