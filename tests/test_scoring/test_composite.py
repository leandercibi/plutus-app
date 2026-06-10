# tests/test_scoring/test_composite.py
import pytest
from plutus.agents.scoring import (
    ScoreBreakdown, Classification, compute_score, _classify,
)

BULL_REGIME  = {"trend": "BULL",  "slope": 0.3, "distance_from_ema50_pct": 2.0}
BEAR_REGIME  = {"trend": "BEAR",  "slope": -0.3, "distance_from_ema50_pct": -2.0}
FLAT_REGIME  = {"trend": "SIDEWAYS", "slope": 0.0, "distance_from_ema50_pct": 0.0}
SECTOR_RS    = {"IT": 1.18, "BANK": 1.05, "PHARMA": 0.95}


# ── _classify tests ──────────────────────────────────────────────────────

def test_classification_buy():
    b75 = ScoreBreakdown(80, 70, 70, 70, 80)   # composite ~75
    assert _classify(b75, position_size=10, material_negative=False, regime_bear=False) == Classification.BUY


def test_classification_watch():
    b60 = ScoreBreakdown(60, 60, 60, 60, 60)   # composite ~60
    assert _classify(b60, position_size=10, material_negative=False, regime_bear=False) == Classification.WATCH


def test_classification_hold():
    b40 = ScoreBreakdown(40, 40, 40, 40, 40)   # composite ~40
    assert _classify(b40, position_size=10, material_negative=False, regime_bear=False) == Classification.HOLD


def test_classification_avoid_low():
    b20 = ScoreBreakdown(20, 20, 20, 20, 20)   # composite ~20
    assert _classify(b20, position_size=10, material_negative=False, regime_bear=False) == Classification.AVOID


def test_material_negative_forces_avoid():
    b_high = ScoreBreakdown(95, 90, 0, 90, 95, hard_avoid_reasons=("material_negative_event",))
    result = _classify(b_high, position_size=10, material_negative=True, regime_bear=False)
    assert result == Classification.AVOID


def test_rr_zero_blocks_buy():
    # High composite but rr=0 → no BUY
    b80 = ScoreBreakdown(95, 90, 90, 90, 0)
    cls = _classify(b80, position_size=10, material_negative=False, regime_bear=False, rr_pillar_score=0)
    assert cls != Classification.BUY


def test_zero_position_size_blocks_buy():
    b80 = ScoreBreakdown(95, 90, 90, 90, 95)
    cls = _classify(b80, position_size=0, material_negative=False, regime_bear=False)
    assert cls != Classification.BUY


# ── compute_score spread test ────────────────────────────────────────────

def test_compute_score_spread_on_fixture(five_symbol_indicators):
    """The 5-symbol fixture must produce a ≥ 40-point composite spread.

    Each symbol gets distinct regime / R:R inputs that amplify the technical
    signal — mirroring real usage where each stock has its own context.
    """
    # Per-symbol context: (regime, sector, levels, news_score, sharpe)
    contexts = {
        "RELIANCE": (
            BULL_REGIME, "IT",
            {"entry": 1000, "stop": 940, "t1": 1120, "t2": 1180},  # R:R=2.0→score≈0 (entry-stop=60, t1-entry=120)
            3.0, 2.5,
        ),
        "HDFCBANK": (
            BULL_REGIME, "BANK",
            {"entry": 1500, "stop": 1440, "t1": 1680, "t2": 1750},  # R:R=3.0→score=100
            2.0, 1.5,
        ),
        "BHARTIARTL": (
            FLAT_REGIME, "IT",
            {"entry": 800, "stop": 768, "t1": 868, "t2": 910},  # R:R=2.13
            0.0, 0.5,
        ),
        "INFY": (
            BEAR_REGIME, "IT",
            {"entry": 1200, "stop": 1152, "t1": 1248, "t2": 1290},  # R:R=1.0→0
            -1.5, -0.5,
        ),
        "TATAMOTORS": (
            BEAR_REGIME, "MEDIA",   # bottom sector
            {"entry": 900, "stop": 855, "t1": 945, "t2": 970},  # R:R=1.0→0
            -3.0, -1.5,
        ),
    }

    fii_stub = {"fii_signal": "neutral"}
    dii_stub = {"dii_signal": "neutral"}
    mf_stub  = {"verdict": "NEUTRAL"}

    scores = {}
    for sym, df in five_symbol_indicators.items():
        regime, sector, levels, news_score, sharpe = contexts[sym]
        news = {"sentiment_score": news_score, "sentiment_label": "neutral", "is_material_event": False}
        breakdown, cls = compute_score(
            symbol=sym,
            indicator_df=df,
            levels=levels,
            news=news,
            fii=fii_stub,
            dii=dii_stub,
            mf=mf_stub,
            nifty_regime=regime,
            sector=sector,
            sector_rs=SECTOR_RS,
            best_bundle_sharpe=sharpe,
            position_size=5,
        )
        scores[sym] = breakdown.composite

    spread = max(scores.values()) - min(scores.values())
    assert spread >= 40, f"Composite spread only {spread} — expected ≥ 40. Scores: {scores}"


def test_fixture_not_all_watch(five_symbol_indicators):
    """At least one BUY and one AVOID on the fixture — no all-WATCH collapse."""
    levels = {"entry": 1000, "stop": 960, "t1": 1080, "t2": 1150}
    news   = {"sentiment_score": 0, "sentiment_label": "neutral", "is_material_event": False}
    fii    = {"fii_signal": "neutral"}
    dii    = {"dii_signal": "neutral"}
    mf     = {"verdict": "NEUTRAL"}

    classifications = {}
    for sym, df in five_symbol_indicators.items():
        _, cls = compute_score(
            symbol=sym, indicator_df=df, levels=levels,
            news=news, fii=fii, dii=dii, mf=mf,
            nifty_regime=BULL_REGIME, sector="IT", sector_rs=SECTOR_RS,
            best_bundle_sharpe=1.5, position_size=5,
        )
        classifications[sym] = cls

    cls_set = set(classifications.values())
    assert len(cls_set) > 1, f"All symbols got same classification — all-WATCH collapse: {classifications}"
