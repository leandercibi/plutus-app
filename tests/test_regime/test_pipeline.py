# tests/test_regime/test_pipeline.py
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from plutus.db.session import Base
from plutus.db.models import MarketRegimeSnapshot
import plutus.data.regime as regime_mod


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_persist_regime_snapshot_writes_row(db_session, synthetic_bull_nifty_df, monkeypatch):
    regime_mod._regime_cache = None
    regime_mod._sector_cache = None
    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv",
                        lambda *a, **kw: synthetic_bull_nifty_df)

    from plutus.data.regime import persist_regime_snapshot
    row = persist_regime_snapshot(db_session, snapshot_date=date(2026, 6, 10))

    rows = db_session.query(MarketRegimeSnapshot).all()
    assert len(rows) == 1
    assert rows[0].snapshot_date == date(2026, 6, 10)
    assert rows[0].nifty_trend in {"BULL", "BEAR", "SIDEWAYS"}


def test_persist_regime_snapshot_upserts(db_session, synthetic_bull_nifty_df, monkeypatch):
    regime_mod._regime_cache = None
    regime_mod._sector_cache = None
    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv",
                        lambda *a, **kw: synthetic_bull_nifty_df)

    from plutus.data.regime import persist_regime_snapshot
    persist_regime_snapshot(db_session, snapshot_date=date(2026, 6, 10))
    regime_mod._regime_cache = None
    regime_mod._sector_cache = None
    persist_regime_snapshot(db_session, snapshot_date=date(2026, 6, 10))

    rows = db_session.query(MarketRegimeSnapshot).all()
    assert len(rows) == 1  # no duplicate
