from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from plutus.config.settings import Settings
from plutus.swing.sentiment.corroboration import HardKillEvaluator
from plutus.swing.sentiment.types import Headline


def _hl(
    title: str,
    source: str,
    entities: list[str] | None = None,
    structural: str | None = None,
) -> Headline:
    return Headline(
        source=source,
        published_at=datetime(2024, 1, 1, 9, 0, 0),
        title=title,
        body=f"structural_event:{structural}" if structural else "",
        entities=entities if entities is not None else [],
    )


def _flat_candles() -> pd.DataFrame:
    # no gap-down, normal volume
    return pd.DataFrame(
        {
            "open": [100.0, 100.5],
            "high": [101.0, 101.0],
            "low": [99.0, 99.5],
            "close": [100.5, 100.8],
            "delivery_adjusted_volume": [1000.0, 1000.0],
        }
    )


@pytest.fixture
def evaluator() -> HardKillEvaluator:
    return HardKillEvaluator(Settings(_env_file=None))


def test_two_independent_entity_headlines_fire(evaluator: HardKillEvaluator) -> None:
    headlines = [
        _hl("INFY fraud probe launched", source="economictimes.com", entities=["INFY"]),
        _hl("INFY scandal deepens", source="moneycontrol.com", entities=["INFY"]),
    ]
    verdict = evaluator.evaluate(headlines, _flat_candles(), "INFY")
    assert verdict.fires is True
    assert verdict.reason == "two_entity_headlines"


def test_two_headlines_same_source_do_not_fire_as_two_entity(
    evaluator: HardKillEvaluator,
) -> None:
    # same source domain -> not independent -> should NOT count as two_entity
    headlines = [
        _hl("INFY fraud probe launched", source="economictimes.com", entities=["INFY"]),
        _hl("INFY scandal deepens", source="economictimes.com", entities=["INFY"]),
    ]
    verdict = evaluator.evaluate(headlines, _flat_candles(), "INFY")
    assert verdict.reason != "two_entity_headlines"
