from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from plutus.config.settings import Settings
from plutus.db.models import Base
from plutus.shared.calibration.recorder import OutcomeRecorder
from plutus.shared.calibration.regime_partition import TradeOutcome


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


def _outcome(r: float, tid: int = 1) -> TradeOutcome:
    return TradeOutcome(
        trade_id=tid,
        bundle="trend",
        regime_at_signal="BULL",
        score_bucket="trend_score_70_75",
        realized_R=r,
        horizon_days=5,
        closed_at=datetime(2025, 1, 1),
        is_paper=False,
    )


def test_first_record_creates_row(session: Session) -> None:
    rec = OutcomeRecorder(Settings(_env_file=None))
    row = rec.record(_outcome(1.0), session)
    session.commit()
    assert row.n_closed == 1
    assert row.win_rate == pytest.approx(1.0)


def test_running_expectancy_updates(session: Session) -> None:
    rec = OutcomeRecorder(Settings(_env_file=None))
    rec.record(_outcome(1.0, 1), session)
    row = rec.record(_outcome(-1.0, 2), session)
    session.commit()
    assert row.n_closed == 2
    assert row.win_rate == pytest.approx(0.5)
    assert row.expectancy_R == pytest.approx(0.0)


def test_ci_ordering_preserved(session: Session) -> None:
    rec = OutcomeRecorder(Settings(_env_file=None))
    for i, r in enumerate([1.0, -0.5, 0.8, -0.3, 1.2]):
        row = rec.record(_outcome(r, i), session)
    session.commit()
    assert row.ci_low_R <= row.expectancy_R <= row.ci_high_R


def test_confidence_band_advances_with_n(session: Session) -> None:
    rec = OutcomeRecorder(Settings(_env_file=None))
    row = None
    for i in range(55):
        row = rec.record(_outcome(0.5, i), session)
    session.commit()
    assert row is not None
    assert row.confidence_band == "high"
