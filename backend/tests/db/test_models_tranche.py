from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from plutus.db.models import AccumulationPosition, Tranche


def _make_position(session: Session, symbol: str = "TCS") -> int:
    pos = AccumulationPosition(
        symbol=symbol,
        state="BUILDING",
        avg_cost=Decimal("3500.00"),
        qty_total=0,
        opened_at=datetime(2025, 1, 1, 10, 0),
        last_thesis_check_at=datetime(2025, 1, 1, 10, 0),
    )
    session.add(pos)
    session.flush()
    return pos.id


def _tranche(position_id: int, seq: int, trigger_pct: float = -0.08) -> Tranche:
    return Tranche(
        position_id=position_id,
        seq=seq,
        atr_normalized_trigger_pct=trigger_pct,
    )


def test_seq_one_to_five_accepted(session: Session) -> None:
    pid = _make_position(session)
    for seq in (1, 2, 3, 4, 5):
        session.add(_tranche(pid, seq=seq))
    session.commit()
    seqs = [
        t.seq for t in session.query(Tranche).filter_by(position_id=pid).order_by(Tranche.seq).all()
    ]
    assert seqs == [1, 2, 3, 4, 5]


def test_seq_zero_rejected(session: Session) -> None:
    pid = _make_position(session)
    session.add(_tranche(pid, seq=0))
    with pytest.raises(IntegrityError):
        session.commit()


def test_seq_six_rejected(session: Session) -> None:
    pid = _make_position(session)
    session.add(_tranche(pid, seq=6))
    with pytest.raises(IntegrityError):
        session.commit()


def test_tranches_ordered_per_position(session: Session) -> None:
    pid = _make_position(session)
    session.add(_tranche(pid, seq=3))
    session.add(_tranche(pid, seq=1))
    session.add(_tranche(pid, seq=2))
    session.commit()
    rows = session.query(Tranche).filter_by(position_id=pid).order_by(Tranche.seq).all()
    assert [t.seq for t in rows] == [1, 2, 3]
