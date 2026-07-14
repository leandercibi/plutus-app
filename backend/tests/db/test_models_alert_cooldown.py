from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from plutus.db.models import AlertCooldown


def test_separate_rows_per_kind_for_same_symbol(session: Session) -> None:
    session.add(
        AlertCooldown(symbol="INFY", kind="SL_WARNING", last_fired_at=datetime(2025, 1, 1, 10))
    )
    session.add(
        AlertCooldown(symbol="INFY", kind="SL_BREACH", last_fired_at=datetime(2025, 1, 1, 11))
    )
    session.commit()
    rows = session.query(AlertCooldown).filter_by(symbol="INFY").all()
    assert {r.kind for r in rows} == {"SL_WARNING", "SL_BREACH"}


def test_fetching_warning_does_not_affect_breach(session: Session) -> None:
    """A16: SL_WARNING and SL_BREACH cooldowns are independent rows."""
    session.add(
        AlertCooldown(symbol="TCS", kind="SL_WARNING", last_fired_at=datetime(2025, 1, 1, 10))
    )
    session.add(
        AlertCooldown(symbol="TCS", kind="SL_BREACH", last_fired_at=datetime(2025, 1, 1, 9))
    )
    session.commit()
    warning = session.query(AlertCooldown).filter_by(symbol="TCS", kind="SL_WARNING").one()
    breach = session.query(AlertCooldown).filter_by(symbol="TCS", kind="SL_BREACH").one()
    assert warning.last_fired_at != breach.last_fired_at
    assert warning.id != breach.id


def test_invalid_kind_rejected(session: Session) -> None:
    session.add(AlertCooldown(symbol="X", kind="BOGUS", last_fired_at=datetime(2025, 1, 1, 10)))
    with pytest.raises(IntegrityError):
        session.commit()
