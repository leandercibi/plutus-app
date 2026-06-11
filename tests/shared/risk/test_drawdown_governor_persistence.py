from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from plutus.config.settings import Settings
from plutus.db.models import Base, DrawdownGovernorState
from plutus.shared.risk.drawdown_governor import DrawdownGovernor


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def governor(session: Session) -> DrawdownGovernor:
    return DrawdownGovernor(Settings(_env_file=None), session)


def test_zero_hwm_never_triggers(governor: DrawdownGovernor) -> None:
    assert governor.current_risk_multiplier(Decimal("0"), Decimal("100")) == 1.0


def test_first_close_starts_clean(governor: DrawdownGovernor, session: Session) -> None:
    governor.record_close(Decimal("1000000"), date(2025, 1, 1))
    session.commit()
    row = session.query(DrawdownGovernorState).one()
    assert row.multiplier == 1.0
    assert row.high_water_mark == Decimal("1000000")
    assert row.consecutive_recovery_days == 0


def test_record_close_same_day_upserts_not_duplicates(
    governor: DrawdownGovernor, session: Session
) -> None:
    d = date(2025, 1, 1)
    governor.record_close(Decimal("1000000"), d)
    session.commit()
    governor.record_close(Decimal("980000"), d)
    session.commit()
    rows = session.query(DrawdownGovernorState).all()
    assert len(rows) == 1
    assert rows[0].pool_value == Decimal("980000")


def test_hwm_rises_with_new_high(governor: DrawdownGovernor, session: Session) -> None:
    governor.record_close(Decimal("1000000"), date(2025, 1, 1))
    session.commit()
    governor.record_close(Decimal("1100000"), date(2025, 1, 2))
    session.commit()
    latest = (
        session.query(DrawdownGovernorState)
        .order_by(DrawdownGovernorState.as_of_date.desc())
        .first()
    )
    assert latest is not None
    assert latest.high_water_mark == Decimal("1100000")


def test_record_close_that_triggers_drawdown_halves(
    governor: DrawdownGovernor, session: Session
) -> None:
    governor.record_close(Decimal("1000000"), date(2025, 1, 1))
    session.commit()
    # 10% drop on the next close -> drawdown triggers, multiplier halves, recovery resets
    governor.record_close(Decimal("900000"), date(2025, 1, 2))
    session.commit()
    latest = (
        session.query(DrawdownGovernorState)
        .order_by(DrawdownGovernorState.as_of_date.desc())
        .first()
    )
    assert latest is not None
    assert latest.multiplier == 0.5
    assert latest.consecutive_recovery_days == 0
