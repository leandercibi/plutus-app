from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from plutus.accumulation.exits.thesis_invalidation import ThesisInvalidationExit
from plutus.accumulation.fundamentals.hard_avoid import FundamentalsSnapshot
from plutus.config.settings import Settings
from plutus.db.models import AccumulationPosition


def _position(state: str = "BUILDING") -> AccumulationPosition:
    return AccumulationPosition(
        symbol="YESBANK",
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
def exit_eval() -> ThesisInvalidationExit:
    return ThesisInvalidationExit(Settings(_env_file=None))


def test_clean_thesis_no_exit(exit_eval: ThesisInvalidationExit) -> None:
    position = _position()
    decision = exit_eval.evaluate(position, _snapshot())
    assert decision.exit is False
    assert position.state == "BUILDING"


@pytest.mark.hallmark
def test_hard_avoid_post_entry_triggers_exit(exit_eval: ThesisInvalidationExit) -> None:
    """B9 hallmark: a hard-avoid condition firing on re-score forces an EXIT even at a
    loss, and the position transitions to EXITED."""
    position = _position()
    decision = exit_eval.evaluate(
        position, _snapshot(going_concern_flag=True, de=3.0)
    )
    assert decision.exit is True
    assert decision.new_state == "EXITED"
    assert position.state == "EXITED"
    assert len(decision.reasons) >= 1


def test_eps_collapse_triggers_exit(exit_eval: ThesisInvalidationExit) -> None:
    position = _position()
    decision = exit_eval.evaluate(position, _snapshot(last_eps_yoy_change=-0.80))
    assert decision.exit is True
    assert position.state == "EXITED"
