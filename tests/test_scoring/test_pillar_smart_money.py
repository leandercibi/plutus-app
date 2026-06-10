# tests/test_scoring/test_pillar_smart_money.py
from plutus.agents.scoring import smart_money_pillar


def test_fii_dii_both_buying_max_score():
    score = smart_money_pillar(
        fii={"fii_net_cr": 5000, "fii_signal": "net_buyer"},
        dii={"dii_net_cr": 3000, "dii_signal": "net_buyer"},
        mf={"verdict": "ACCUMULATING", "mf_count_accumulating": 5, "mf_count_reducing": 0},
    )
    assert score >= 85


def test_both_selling_min_score():
    score = smart_money_pillar(
        fii={"fii_signal": "net_seller"},
        dii={"dii_signal": "net_seller"},
        mf={"verdict": "REDUCING", "mf_count_accumulating": 0, "mf_count_reducing": 4},
    )
    assert score <= 25


def test_unknown_mf_degrades_gracefully():
    score = smart_money_pillar(
        fii={"fii_signal": "net_buyer"},
        dii={"dii_signal": "neutral"},
        mf={"verdict": "UNKNOWN", "mf_count_accumulating": 0, "mf_count_reducing": 0},
    )
    assert 40 <= score <= 70


def test_one_side_buying_moderate():
    score = smart_money_pillar(
        fii={"fii_signal": "net_buyer"},
        dii={"dii_signal": "neutral"},
        mf={"verdict": "NEUTRAL"},
    )
    assert 45 <= score <= 75


def test_empty_inputs_returns_neutral():
    score = smart_money_pillar(fii={}, dii={}, mf={})
    assert 30 <= score <= 70
