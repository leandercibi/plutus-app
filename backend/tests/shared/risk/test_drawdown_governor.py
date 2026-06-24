from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from plutus.config.settings import Settings
from plutus.db.models import Base
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


def test_below_trigger_multiplier_is_one(governor: DrawdownGovernor) -> None:
    # 5% drawdown < 7% trigger
    mult = governor.current_risk_multiplier(
        pool_high_water_mark=Decimal("1000000"), pool_value=Decimal("950000")
    )
    assert mult == 1.0


def test_at_trigger_multiplier_halves(governor: DrawdownGovernor) -> None:
    # 8% drawdown > 7% trigger
    mult = governor.current_risk_multiplier(
        pool_high_water_mark=Decimal("1000000"), pool_value=Decimal("920000")
    )
    assert mult == 0.5


def test_three_recovery_days_restore_to_one(
    governor: DrawdownGovernor, session: Session
) -> None:
    hwm = Decimal("1000000")
    d0 = date(2025, 1, 1)
    # trigger the drawdown
    governor.current_risk_multiplier(hwm, Decimal("910000"))
    governor.record_close(Decimal("910000"), d0)
    session.commit()
    # three consecutive recovery closes (above the trigger threshold)
    for i in range(1, 4):
        governor.record_close(Decimal("960000"), d0 + timedelta(days=i))
        session.commit()
    mult = governor.current_risk_multiplier(hwm, Decimal("960000"))
    assert mult == 1.0


def test_two_recovery_then_dip_stays_halved(
    governor: DrawdownGovernor, session: Session
) -> None:
    hwm = Decimal("1000000")
    d0 = date(2025, 1, 1)
    governor.current_risk_multiplier(hwm, Decimal("910000"))
    governor.record_close(Decimal("910000"), d0)
    session.commit()
    governor.record_close(Decimal("960000"), d0 + timedelta(days=1))
    session.commit()
    governor.record_close(Decimal("960000"), d0 + timedelta(days=2))
    session.commit()
    # dip back below the trigger threshold on day 3 -> recovery counter resets
    governor.record_close(Decimal("905000"), d0 + timedelta(days=3))
    session.commit()
    mult = governor.current_risk_multiplier(hwm, Decimal("905000"))
    assert mult == 0.5
