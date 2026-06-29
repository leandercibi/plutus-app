from __future__ import annotations

import pytest

from plutus.accumulation.fundamentals.quality import Quality


@pytest.fixture
def quality() -> Quality:
    return Quality()


def test_high_roce_low_de_positive_fcf_scores_max(quality: Quality) -> None:
    score = quality.score(roce=0.35, de=0.1, fcf_margin=0.25)
    assert score == 30


def test_low_quality_scores_low(quality: Quality) -> None:
    score = quality.score(roce=0.05, de=2.5, fcf_margin=-0.10)
    assert score < 10


def test_score_bounded_0_to_30(quality: Quality) -> None:
    high = quality.score(roce=1.0, de=0.0, fcf_margin=1.0)
    low = quality.score(roce=-0.5, de=10.0, fcf_margin=-1.0)
    assert 0 <= high <= 30
    assert 0 <= low <= 30


def test_higher_roce_increases_score(quality: Quality) -> None:
    low = quality.score(roce=0.10, de=0.5, fcf_margin=0.10)
    high = quality.score(roce=0.30, de=0.5, fcf_margin=0.10)
    assert high > low


def test_lower_de_increases_score(quality: Quality) -> None:
    high_de = quality.score(roce=0.20, de=2.0, fcf_margin=0.10)
    low_de = quality.score(roce=0.20, de=0.2, fcf_margin=0.10)
    assert low_de > high_de
