from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from plutus.config.settings import Settings
from plutus.swing.sentiment.corroboration import HardKillEvaluator
from plutus.swing.sentiment.types import Headline


def _hl(title: str, source: str, entities: list[str] | None = None) -> Headline:
    return Headline(
        source=source,
        published_at=datetime(2024, 1, 1, 9, 0, 0),
        title=title,
        body="",
        entities=entities if entities is not None else [],
    )


def _gap_down_high_volume() -> pd.DataFrame:
    # prior close 100, today opens at 95 (gap-down), delivery volume 2x prior median
    return pd.DataFrame(
        {
            "open": [100.0, 95.0],
            "high": [101.0, 96.0],
            "low": [99.0, 93.0],
            "close": [100.0, 94.0],
            "delivery_adjusted_volume": [1000.0, 2000.0],
        }
    )


def _flat_normal_volume() -> pd.DataFrame:
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


def test_headline_plus_gap_down_volume_fires(evaluator: HardKillEvaluator) -> None:
    headlines = [
        _hl(
            "INFY warns of weak guidance", source="economictimes.com", entities=["INFY"]
        )
    ]
    verdict = evaluator.evaluate(headlines, _gap_down_high_volume(), "INFY")
    assert verdict.fires is True
    assert verdict.reason == "headline_plus_pricevol"


def test_headline_without_pricevol_does_not_fire_via_pricevol(
    evaluator: HardKillEvaluator,
) -> None:
    headlines = [
        _hl(
            "INFY warns of weak guidance", source="economictimes.com", entities=["INFY"]
        )
    ]
    verdict = evaluator.evaluate(headlines, _flat_normal_volume(), "INFY")
    assert verdict.reason != "headline_plus_pricevol"
    assert verdict.fires is False
