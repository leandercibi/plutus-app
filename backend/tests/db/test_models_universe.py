from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from plutus.db.models import Universe


def _row(symbol: str, d: date, mtv: Decimal = Decimal("100000000")) -> Universe:
    return Universe(
        symbol=symbol,
        as_of_date=d,
        median_traded_value_inr=mtv,
        in_universe=True,
    )


def test_unique_symbol_as_of_date(session: Session) -> None:
    session.add(_row("INFY", date(2025, 1, 1)))
    session.commit()
    session.add(_row("INFY", date(2025, 1, 1)))
    with pytest.raises(IntegrityError):
        session.commit()


def test_pit_round_trip_three_dates(session: Session) -> None:
    for d in (date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 1)):
        session.add(_row("TCS", d))
    session.commit()
    rows = session.query(Universe).filter_by(symbol="TCS").order_by(Universe.as_of_date).all()
    assert [r.as_of_date for r in rows] == [
        date(2025, 1, 1),
        date(2025, 2, 1),
        date(2025, 3, 1),
    ]


def test_reject_negative_median_traded_value(session: Session) -> None:
    session.add(_row("HDFC", date(2025, 1, 1), mtv=Decimal("-1")))
    with pytest.raises(IntegrityError):
        session.commit()
