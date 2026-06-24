from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from plutus.db.models import SwingSignal, SwingTrade


def _make_signal(session: Session, symbol: str = "INFY") -> int:
    sig = SwingSignal(
        run_id="run-001",
        symbol=symbol,
        bundle="trend",
        score=78,
        label="BUY",
        entry=Decimal("1500.00"),
        stop_loss=Decimal("1450.00"),
        target_1=Decimal("1600.00"),
        target_2=Decimal("1700.00"),
        expectancy_R=0.42,
        drawn_rr=1.8,
        regime_at_signal="BULL",
        pillar_breakdown_json={"trend": 30},
        counterfactual_text=None,
        created_at=datetime(2025, 1, 1, 9, 15),
    )
    session.add(sig)
    session.flush()
    return sig.id


def _trade(
    signal_id: int,
    state: str = "OPEN",
    closed_at: datetime | None = None,
    realized_R: float | None = None,
) -> SwingTrade:
    return SwingTrade(
        signal_id=signal_id,
        symbol="INFY",
        bundle="trend",
        state=state,
        opened_at=datetime(2025, 1, 2, 9, 15),
        closed_at=closed_at,
        qty=100,
        risk_R=1.0,
        exit_reason=None,
        realized_R=realized_R,
        mfe_R=None,
        mae_R=None,
    )


def test_valid_states_accepted(session: Session) -> None:
    sid = _make_signal(session)
    for state in ("OPEN", "T1_HIT", "SCRATCHED", "EXPIRED"):
        session.add(_trade(sid, state=state))
    session.commit()
    states = {t.state for t in session.query(SwingTrade).all()}
    assert states == {"OPEN", "T1_HIT", "SCRATCHED", "EXPIRED"}


def test_invalid_state_rejected(session: Session) -> None:
    sid = _make_signal(session)
    session.add(_trade(sid, state="PARTIAL"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_close_win_requires_closed_at_and_realized_r(session: Session) -> None:
    sid = _make_signal(session)
    session.add(_trade(sid, state="CLOSED_WIN", closed_at=None, realized_R=None))
    with pytest.raises(IntegrityError):
        session.commit()


def test_close_loss_with_required_fields_accepted(session: Session) -> None:
    sid = _make_signal(session)
    session.add(
        _trade(
            sid,
            state="CLOSED_LOSS",
            closed_at=datetime(2025, 1, 10, 15, 0),
            realized_R=-1.0,
        )
    )
    session.commit()
    row = session.query(SwingTrade).one()
    assert row.state == "CLOSED_LOSS"
    assert row.closed_at == datetime(2025, 1, 10, 15, 0)
    assert row.realized_R == pytest.approx(-1.0)
