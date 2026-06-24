from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from plutus.db.models import RegimeSnapshot


def _row(
    d: date,
    label: str = "BULL",
    breadth_confirmed_flip: bool = False,
) -> RegimeSnapshot:
    return RegimeSnapshot(
        as_of_date=d,
        label=label,
        nifty_close=Decimal("22000.50"),
        pct_above_50dma=0.62,
        pct_above_200dma=0.71,
        advance_decline=1.8,
        india_vix=13.4,
        fii_flow_inr=Decimal("1500000000"),
        dii_flow_inr=Decimal("800000000"),
        breadth_confirmed_flip=breadth_confirmed_flip,
    )


def test_valid_labels_accepted(session: Session) -> None:
    for i, label in enumerate(("BULL", "BEAR", "SIDEWAYS")):
        session.add(_row(date(2025, 1, 1 + i), label=label))
    session.commit()
    labels = {r.label for r in session.query(RegimeSnapshot).all()}
    assert labels == {"BULL", "BEAR", "SIDEWAYS"}


def test_invalid_label_rejected(session: Session) -> None:
    session.add(_row(date(2025, 1, 1), label="NEUTRAL"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_breadth_confirmed_flip_persists(session: Session) -> None:
    session.add(_row(date(2025, 1, 1), label="BULL", breadth_confirmed_flip=False))
    session.add(_row(date(2025, 1, 2), label="BEAR", breadth_confirmed_flip=True))
    session.commit()
    yesterday = session.get(RegimeSnapshot, date(2025, 1, 1))
    today = session.get(RegimeSnapshot, date(2025, 1, 2))
    assert yesterday is not None
    assert today is not None
    assert yesterday.breadth_confirmed_flip is False
    assert today.breadth_confirmed_flip is True
    assert today.label != yesterday.label
