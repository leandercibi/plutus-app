from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from plutus.db.models import AccumulationPosition


def _position(
    symbol: str = "TCS",
    state: str = "BUILDING",
    qty_total: int = 50,
) -> AccumulationPosition:
    return AccumulationPosition(
        symbol=symbol,
        state=state,
        avg_cost=Decimal("3500.00"),
        qty_total=qty_total,
        opened_at=datetime(2025, 1, 1, 10, 0),
        last_thesis_check_at=datetime(2025, 1, 1, 10, 0),
    )


def test_valid_states_accepted(session: Session) -> None:
    states = ("BUILDING", "FULL", "PAUSED", "EXITED", "CONVERTED_TO_SWING")
    for i, state in enumerate(states):
        session.add(_position(symbol=f"SYM{i}", state=state))
    session.commit()
    persisted = {p.state for p in session.query(AccumulationPosition).all()}
    assert persisted == set(states)


def test_invalid_state_rejected(session: Session) -> None:
    session.add(_position(state="CLOSING"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_qty_total_zero_allowed(session: Session) -> None:
    session.add(_position(qty_total=0))
    session.commit()
    row = session.query(AccumulationPosition).one()
    assert row.qty_total == 0


def test_qty_total_negative_rejected(session: Session) -> None:
    session.add(_position(qty_total=-1))
    with pytest.raises(IntegrityError):
        session.commit()
