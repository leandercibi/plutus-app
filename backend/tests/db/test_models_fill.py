from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from plutus.db.models import Fill, SwingSignal, SwingTrade


def _make_trade(session: Session) -> int:
    sig = SwingSignal(
        run_id="run-001",
        symbol="INFY",
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
    trade = SwingTrade(
        signal_id=sig.id,
        symbol="INFY",
        bundle="trend",
        state="OPEN",
        opened_at=datetime(2025, 1, 2, 9, 15),
        qty=100,
        risk_R=1.0,
    )
    session.add(trade)
    session.flush()
    return trade.id


def _fill(
    trade_id: int,
    kind: str = "MOCK",
    side: str = "BUY",
    price: Decimal = Decimal("1502.00"),
) -> Fill:
    return Fill(
        trade_id=trade_id,
        kind=kind,
        side=side,
        qty=100,
        price=price,
        cost_inr=Decimal("25.50"),
        slippage_bps=5.0,
        filled_at=datetime(2025, 1, 2, 9, 16),
    )


def test_mock_and_real_kinds_accepted(session: Session) -> None:
    tid = _make_trade(session)
    session.add(_fill(tid, kind="MOCK"))
    session.add(_fill(tid, kind="REAL"))
    session.commit()
    kinds = {f.kind for f in session.query(Fill).all()}
    assert kinds == {"MOCK", "REAL"}


def test_invalid_kind_rejected(session: Session) -> None:
    tid = _make_trade(session)
    session.add(_fill(tid, kind="SIMULATED"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_side_rejected(session: Session) -> None:
    tid = _make_trade(session)
    session.add(_fill(tid, side="SHORT"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_mock_and_real_coexist_for_same_trade(session: Session) -> None:
    tid = _make_trade(session)
    session.add(_fill(tid, kind="MOCK", price=Decimal("1502.00")))
    session.add(_fill(tid, kind="REAL", price=Decimal("1504.25")))
    session.commit()
    fills = session.query(Fill).filter_by(trade_id=tid).order_by(Fill.kind).all()
    assert len(fills) == 2
    by_kind = {f.kind: f.price for f in fills}
    assert by_kind["MOCK"] == Decimal("1502.00")
    assert by_kind["REAL"] == Decimal("1504.25")
