from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from plutus.config.settings import Settings
from plutus.swing.sentiment.corroboration import HardKillEvaluator
from plutus.swing.sentiment.types import Headline


def _flat_candles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0, 100.2],
            "high": [101.0, 101.0],
            "low": [99.0, 99.8],
            "close": [100.0, 100.5],
            "delivery_adjusted_volume": [1000.0, 1000.0],
        }
    )


@pytest.fixture
def evaluator() -> HardKillEvaluator:
    return HardKillEvaluator(Settings(_env_file=None))


def test_single_uncorroborated_headline_does_not_kill(
    evaluator: HardKillEvaluator,
) -> None:
    headlines = [
        Headline(
            source="economictimes.com",
            published_at=datetime(2024, 1, 1, 9, 0, 0),
            title="INFY faces minor concern in one segment",
            body="",
            entities=["INFY"],
        )
    ]
    verdict = evaluator.evaluate(headlines, _flat_candles(), "INFY")
    assert verdict.fires is False
    assert verdict.reason == "uncorroborated"
    assert 0 <= verdict.penalty_only <= 3


def test_no_evidence_zero_penalty(evaluator: HardKillEvaluator) -> None:
    verdict = evaluator.evaluate([], _flat_candles(), "INFY")
    assert verdict.fires is False
    assert verdict.reason == "uncorroborated"
    assert verdict.penalty_only == 0


def test_uncorroborated_penalty_capped_at_3(evaluator: HardKillEvaluator) -> None:
    # many low/medium-confidence headlines -> graded penalty, capped at 3, no kill
    headlines = [
        Headline(
            source="blog-aggregator.com",
            published_at=datetime(2024, 1, 1, 9, 0, 0),
            title="INFY rumor concern weak chatter",
            body="",
            entities=["INFY"],
        )
        for _ in range(20)
    ]
    verdict = evaluator.evaluate(headlines, _flat_candles(), "INFY")
    assert verdict.fires is False
    assert verdict.penalty_only <= 3
