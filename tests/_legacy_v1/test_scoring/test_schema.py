# tests/test_scoring/test_schema.py
from plutus.agents.scoring import ScoreBreakdown, Classification, PILLAR_WEIGHTS


def test_score_breakdown_composite():
    b = ScoreBreakdown(technical=80, smart_money=50, sentiment=60, regime=70, rr=90)
    expected = round(80 * 0.40 + 50 * 0.15 + 60 * 0.15 + 70 * 0.15 + 90 * 0.15)
    assert b.composite == expected
    assert isinstance(b.composite, int)


def test_classification_enum_values():
    assert {c.value for c in Classification} == {"BUY", "WATCH", "HOLD", "AVOID"}


def test_pillar_weights_sum_to_1():
    assert abs(sum(PILLAR_WEIGHTS.values()) - 1.0) < 1e-10


def test_score_breakdown_immutable():
    b = ScoreBreakdown(80, 50, 60, 70, 90)
    try:
        b.technical = 99
        assert False, "should be immutable"
    except (AttributeError, TypeError):
        pass


def test_hard_avoid_reasons_default_empty():
    b = ScoreBreakdown(50, 50, 50, 50, 50)
    assert b.hard_avoid_reasons == ()
