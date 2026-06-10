# tests/test_scoring/test_pillar_technical.py
import pytest
from plutus.agents.scoring import technical_pillar


def test_uptrend_scores_high(uptrend_df):
    score = technical_pillar(uptrend_df, best_bundle_sharpe=2.5)
    assert score >= 60, f"Expected >= 60 for strong uptrend, got {score}"


def test_downtrend_scores_low(downtrend_df):
    score = technical_pillar(downtrend_df, best_bundle_sharpe=-1.5)
    assert score <= 50, f"Expected <= 50 for downtrend, got {score}"


def test_pillar_returns_0_100_range(five_symbol_indicators):
    for sym, df in five_symbol_indicators.items():
        score = technical_pillar(df, best_bundle_sharpe=1.0)
        assert 0 <= score <= 100, f"{sym}: score {score} out of range"


def test_spread_on_fixture(five_symbol_indicators):
    scores = {
        sym: technical_pillar(df, best_bundle_sharpe=1.0)
        for sym, df in five_symbol_indicators.items()
    }
    spread = max(scores.values()) - min(scores.values())
    assert spread >= 20, f"Technical spread only {spread:.1f} — expected ≥ 20"


def test_high_sharpe_boosts_score(uptrend_df):
    low  = technical_pillar(uptrend_df, best_bundle_sharpe=-2.0)
    high = technical_pillar(uptrend_df, best_bundle_sharpe=3.0)
    assert high > low


def test_empty_df_does_not_crash():
    import pandas as pd
    empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    score = technical_pillar(empty, best_bundle_sharpe=0.0)
    assert 0 <= score <= 100
