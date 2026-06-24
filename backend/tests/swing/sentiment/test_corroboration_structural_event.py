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


def test_structural_event_rating_downgrade_fires(evaluator: HardKillEvaluator) -> None:
    headlines = [
        Headline(
            source="rating-agency.com",
            published_at=datetime(2024, 1, 1, 9, 0, 0),
            title="INFY rating downgraded by agency",
            body="structural_event:rating_downgrade",
            entities=["INFY"],
        )
    ]
    verdict = evaluator.evaluate(headlines, _flat_candles(), "INFY")
    assert verdict.fires is True
    assert verdict.reason == "structural_event"


def test_structural_event_for_other_symbol_does_not_fire(
    evaluator: HardKillEvaluator,
) -> None:
    headlines = [
        Headline(
            source="rating-agency.com",
            published_at=datetime(2024, 1, 1, 9, 0, 0),
            title="RELIANCE rating downgraded by agency",
            body="structural_event:rating_downgrade",
            entities=["RELIANCE"],
        )
    ]
    verdict = evaluator.evaluate(headlines, _flat_candles(), "INFY")
    assert verdict.fires is False
