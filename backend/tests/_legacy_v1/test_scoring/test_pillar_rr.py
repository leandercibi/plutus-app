# tests/test_scoring/test_pillar_rr.py
import pytest
from plutus.agents.scoring import rr_pillar


def test_rr_below_1_5_zeros():
    # R:R=1.4: entry=100, stop=98 → risk=2; t1=102.8 → reward=2.8 → R:R=1.4
    assert rr_pillar(entry=100, stop=98, t1=102.8, t2=104) == 0


def test_rr_exactly_1_5_is_zero():
    # R:R=1.5: entry=100, stop=98 → risk=2; t1=103 → reward=3 → R:R=1.5 → floor, score=0
    score = rr_pillar(entry=100, stop=98, t1=103, t2=104)
    assert score == pytest.approx(0.0, abs=1.0)


def test_rr_2_0_is_50():
    # R:R=2.0: entry=100, stop=98 → risk=2; t1=104 → reward=4 → (2.0-1.5)*100=50
    score = rr_pillar(entry=100, stop=98, t1=104, t2=106)
    assert score == pytest.approx(50.0, abs=1.0)


def test_rr_2_5_is_100():
    # R:R=2.5: entry=100, stop=98 → risk=2; t1=105 → reward=5 → (2.5-1.5)*100=100
    score = rr_pillar(entry=100, stop=98, t1=105, t2=107)
    assert score == pytest.approx(100.0, abs=1.0)


def test_rr_above_2_5_capped():
    # R:R=5.0: entry=100, stop=98 → capped at 100
    assert rr_pillar(entry=100, stop=98, t1=110, t2=115) == 100


def test_zero_entry_safe():
    assert rr_pillar(entry=0, stop=0, t1=0, t2=0) == 0


def test_negative_entry_safe():
    # entry=-10, stop=0, t1=10 → risk=10, reward=20, R:R=2.0 → (2.0-1.5)*100=50
    # No crash; result is a valid score
    assert rr_pillar(entry=-10, stop=0, t1=10, t2=20) == pytest.approx(50.0, abs=1.0)
