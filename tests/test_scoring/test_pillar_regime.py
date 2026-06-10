# tests/test_scoring/test_pillar_regime.py
import pytest
from plutus.agents.scoring import regime_pillar

SECTOR_RS_EXAMPLE = {
    "IT": 1.18, "BANK": 1.12, "AUTO": 1.08,
    "FMCG": 1.02, "PHARMA": 1.00, "METAL": 0.92,
    "REALTY": 0.88, "ENERGY": 0.85, "INFRA": 0.82,
    "PSE": 0.79, "MEDIA": 0.75,
}


def test_bull_regime_top_sector_max_score():
    score = regime_pillar(
        nifty_regime={"trend": "BULL", "slope": 0.5, "distance_from_ema50_pct": 3.5},
        sector="IT",
        sector_rs=SECTOR_RS_EXAMPLE,
    )
    assert score >= 80, f"BULL + top sector expected >= 80, got {score}"


def test_bear_regime_weak_sector_min_score():
    score = regime_pillar(
        nifty_regime={"trend": "BEAR", "slope": -0.4, "distance_from_ema50_pct": -2.1},
        sector="MEDIA",
        sector_rs=SECTOR_RS_EXAMPLE,
    )
    assert score <= 30, f"BEAR + bottom sector expected <= 30, got {score}"


def test_sideways_regime_moderate():
    score = regime_pillar(
        nifty_regime={"trend": "SIDEWAYS", "slope": 0.0, "distance_from_ema50_pct": 0.2},
        sector="FMCG",
        sector_rs=SECTOR_RS_EXAMPLE,
    )
    assert 30 <= score <= 70, f"SIDEWAYS expected 30-70, got {score}"


def test_unknown_regime_neutral():
    score = regime_pillar(
        nifty_regime={},
        sector=None,
        sector_rs={},
    )
    assert 30 <= score <= 70


def test_returns_0_100():
    for trend in ["BULL", "BEAR", "SIDEWAYS", "UNKNOWN"]:
        score = regime_pillar(
            nifty_regime={"trend": trend, "slope": 0.1},
            sector="IT",
            sector_rs=SECTOR_RS_EXAMPLE,
        )
        assert 0 <= score <= 100, f"trend={trend} score {score} out of range"
