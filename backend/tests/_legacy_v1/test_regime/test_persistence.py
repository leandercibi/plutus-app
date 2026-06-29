# tests/test_regime/test_persistence.py
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from plutus.db.session import Base
from plutus.db.models import MarketRegimeSnapshot


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_market_regime_snapshot_persists(db_session):
    snap = MarketRegimeSnapshot(
        snapshot_date=date(2026, 6, 1),
        nifty_trend="BULL",
        nifty_slope=0.45,
        distance_from_ema50_pct=3.5,
        sector_rs={"IT": 1.18, "BANK": 1.05},
    )
    db_session.add(snap)
    db_session.commit()

    row = (
        db_session.query(MarketRegimeSnapshot)
        .filter_by(snapshot_date=date(2026, 6, 1))
        .one()
    )
    assert row.nifty_trend == "BULL"
    assert pytest.approx(row.sector_rs["IT"], rel=1e-3) == 1.18


def test_snapshot_unique_per_date(db_session):
    for _ in range(2):
        try:
            snap = MarketRegimeSnapshot(
                snapshot_date=date(2026, 6, 2),
                nifty_trend="BEAR",
                nifty_slope=-0.1,
                distance_from_ema50_pct=-2.0,
                sector_rs={},
            )
            db_session.add(snap)
            db_session.commit()
        except Exception:
            db_session.rollback()

    rows = (
        db_session.query(MarketRegimeSnapshot)
        .filter_by(snapshot_date=date(2026, 6, 2))
        .all()
    )
    assert len(rows) == 1


def test_snapshot_null_sector_rs_allowed(db_session):
    snap = MarketRegimeSnapshot(
        snapshot_date=date(2026, 6, 3),
        nifty_trend="SIDEWAYS",
        nifty_slope=0.0,
        distance_from_ema50_pct=0.5,
        sector_rs=None,
    )
    db_session.add(snap)
    db_session.commit()
    row = (
        db_session.query(MarketRegimeSnapshot)
        .filter_by(snapshot_date=date(2026, 6, 3))
        .one()
    )
    assert row.sector_rs is None
