from __future__ import annotations

import datetime as _dt
from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from plutus.db.models import Base
from plutus.shared.regime.detector import RegimeInputs, RegimeVerdict
from plutus.shared.regime.snapshot import read_snapshot, save_snapshot


@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_conn: object, _rec: object) -> None:
    cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


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


def _inputs() -> RegimeInputs:
    return RegimeInputs(
        nifty_close=Decimal("22000.50"),
        nifty_50dma=Decimal("21000"),
        nifty_200dma=Decimal("20000"),
        pct_above_50dma=0.70,
        pct_above_200dma=0.65,
        advance_decline=1.5,
        india_vix=14.0,
        fii_flow_5d_sum_inr=Decimal("5000000000.00"),
        dii_flow_5d_sum_inr=Decimal("3000000000.00"),
        pct_above_50dma_5d_ago=0.55,
    )


def _verdict() -> RegimeVerdict:
    return RegimeVerdict(
        label="BULL",
        confidence="high",
        reasons=["nifty above 200DMA"],
        breadth_confirmed=True,
    )


def test_snapshot_round_trip(session: Session) -> None:
    as_of = _dt.date(2025, 3, 10)
    save_snapshot(as_of, _verdict(), _inputs(), session=session)
    session.commit()

    row = read_snapshot(as_of, session=session)
    assert row is not None
    assert row.label == "BULL"
    assert row.breadth_confirmed_flip is True
    assert row.nifty_close == Decimal("22000.50")
    assert row.pct_above_50dma == pytest.approx(0.70)
    assert row.india_vix == pytest.approx(14.0)
    assert row.fii_flow_inr == Decimal("5000000000.00")
    assert row.dii_flow_inr == Decimal("3000000000.00")


def test_read_missing_snapshot_returns_none(session: Session) -> None:
    assert read_snapshot(_dt.date(2099, 1, 1), session=session) is None
