from __future__ import annotations

from datetime import datetime
from decimal import Decimal

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


def _clean_snapshot() -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        de=0.5,
        is_financial=False,
        last_eps_yoy_change=0.12,
        improving_guidance=True,
        going_concern_flag=False,
        promoter_pledge_increase_pp=0.0,
        roce=0.22,
        fcf_margin=0.18,
        pe_ttm=16.0,
    )


def test_stable_fundamentals_pass_through() -> None:
    revalidator = TrancheRevalidator(Settings(_env_file=None))
    position = _position()
    outcome = revalidator.revalidate(
        position,
        latest_fundamentals=_clean_snapshot(),
        prior_quality_score=27,
        current_quality_score=26,  # 1-point drop, within tolerance
    )
    assert outcome.ok is True
    assert outcome.reasons == []
    # the position is NOT paused; the next tranche may fire
    assert position.state == "BUILDING"


def test_small_quality_improvement_passes() -> None:
    revalidator = TrancheRevalidator(Settings(_env_file=None))
    position = _position()
    outcome = revalidator.revalidate(
        position,
        latest_fundamentals=_clean_snapshot(),
        prior_quality_score=24,
        current_quality_score=29,  # improved
    )
    assert outcome.ok is True
    assert position.state == "BUILDING"
