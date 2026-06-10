# tests/test_scoring/test_persistence.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from plutus.db.session import Base
from plutus.db.models import Recommendation, RecommendationVerdict


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_recommendation_persists_sub_scores(db_session):
    rec = Recommendation(
        symbol="RELIANCE",
        recommendation=RecommendationVerdict.BUY,
        confidence=75,
        technical_score=80,
        sentiment_score=60,
        smart_money_score=70,
        regime_score=80,
        rr_score=90,
    )
    db_session.add(rec)
    db_session.commit()

    row = db_session.query(Recommendation).filter_by(symbol="RELIANCE").one()
    assert row.regime_score == 80
    assert row.rr_score == 90
    assert row.confidence == 75


def test_regime_rr_score_nullable(db_session):
    rec = Recommendation(
        symbol="INFY",
        recommendation=RecommendationVerdict.WATCH,
        confidence=60,
    )
    db_session.add(rec)
    db_session.commit()

    row = db_session.query(Recommendation).filter_by(symbol="INFY").one()
    assert row.regime_score is None
    assert row.rr_score is None
