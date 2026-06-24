from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from plutus.accumulation.fundamentals.hard_avoid import FundamentalsSnapshot
from plutus.accumulation.tranches.revalidation import TrancheRevalidator
from plutus.config.settings import Settings
from plutus.db.models import AccumulationPosition


def _position(state: str = "BUILDING") -> AccumulationPosition:
    return AccumulationPosition(
        symbol="TCS",
        state=state,
        avg_cost=Decimal("100"),
        qty_total=2000,
        opened_at=datetime(2024, 1, 1),
        last_thesis_check_at=datetime(2024, 2, 1),
    )


def _snapshot(**overrides: object) -> FundamentalsSnapshot:
    base: dict[str, object] = {
        "de": 0.5,
        "is_financial": False,
        "last_eps_yoy_change": 0.10,
        "improving_guidance": False,
        "going_concern_flag": False,
        "promoter_pledge_increase_pp": 0.0,
        "roce": 0.20,
        "fcf_margin": 0.15,
        "pe_ttm": 18.0,
    }
    base.update(overrides)
    return FundamentalsSnapshot(**base)  # type: ignore[arg-type]


@pytest.fixture
def revalidator() -> TrancheRevalidator:
    return TrancheRevalidator(Settings(_env_file=None))


@pytest.mark.hallmark
def test_quality_drop_over_10_points_fails_and_pauses(
    revalidator: TrancheRevalidator,
) -> None:
    """A13 hallmark: quality pillar dropping > 10 points between tranches fails
    revalidation and pauses the position."""
    position = _position()
    outcome = revalidator.revalidate(
        position,
        latest_fundamentals=_snapshot(),
        prior_quality_score=28,
        current_quality_score=15,  # 13-point drop
    )
    assert outcome.ok is False
    assert position.state == "PAUSED"
    assert any("quality" in r.lower() for r in outcome.reasons)


def test_hard_avoid_fire_fails_and_pauses(revalidator: TrancheRevalidator) -> None:
    position = _position()
    outcome = revalidator.revalidate(
        position,
        latest_fundamentals=_snapshot(going_concern_flag=True),
        prior_quality_score=28,
        current_quality_score=27,
    )
    assert outcome.ok is False
    assert position.state == "PAUSED"


def test_eps_collapse_fails(revalidator: TrancheRevalidator) -> None:
    position = _position()
    outcome = revalidator.revalidate(
        position,
        latest_fundamentals=_snapshot(last_eps_yoy_change=-0.70),
        prior_quality_score=28,
        current_quality_score=27,
    )
    assert outcome.ok is False
    assert position.state == "PAUSED"
