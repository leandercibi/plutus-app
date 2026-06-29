from __future__ import annotations

import numpy as np
import pandas as pd

from plutus.swing.scoring.pillars import technical_score


def _trending_candles() -> pd.DataFrame:
    n = 220
    base = np.linspace(100, 160, n)
    return pd.DataFrame(
        {
            "open": base,
            "high": base + 1.0,
            "low": base - 1.0,
            "close": base,
        }
    )


def test_technical_score_is_bounded_0_to_30() -> None:
    score = technical_score(_trending_candles())
    assert 0 <= score.total <= 30


def test_uptrend_scores_higher_than_downtrend() -> None:
    up = technical_score(_trending_candles())
    down_base = np.linspace(160, 100, 220)
    down = technical_score(
        pd.DataFrame(
            {
                "open": down_base,
                "high": down_base + 1.0,
                "low": down_base - 1.0,
                "close": down_base,
            }
        )
    )
    assert up.total > down.total


def test_atr_percentile_and_mean_reversion_contribute() -> None:
    score = technical_score(_trending_candles())
    assert score.atr_percentile >= 0.0
    assert score.mean_reversion >= 0.0
