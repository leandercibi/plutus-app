from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from plutus.config.settings import Settings
from plutus.db.models import Base, CalibrationRow
from plutus.shared.calibration.lookup import DBCalibrationLookup


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


def _row(bucket: str, regime: str, n: int, win_rate: float) -> CalibrationRow:
    return CalibrationRow(
        bucket=bucket,
        regime=regime,
        n_closed=n,
        win_rate=win_rate,
        expectancy_R=0.4,
        ci_low_R=0.1,
        ci_high_R=0.7,
        sprt_state="continue",
        last_updated=datetime(2025, 1, 1),
        confidence_band="high" if n >= 50 else "low",
    )


def test_hit_rate_uses_regime_row_when_sample_sufficient(session: Session) -> None:
    session.add(_row("trend_70_75", "BULL", 60, 0.65))
    session.commit()
    lookup = DBCalibrationLookup(session, Settings(_env_file=None))
    assert lookup.hit_rate("trend", "BULL", "target_1") == pytest.approx(0.65)


def test_hit_rate_falls_back_to_pooled_when_sample_small(session: Session) -> None:
    # BULL has only n=5 (below floor); pooled across regimes should be used
    session.add(_row("trend_70_75", "BULL", 5, 0.30))
    session.add(_row("trend_70_75", "BEAR", 100, 0.50))
    session.commit()
    lookup = DBCalibrationLookup(session, Settings(_env_file=None))
    rate = lookup.hit_rate("trend", "BULL", "target_1")
    # pooled weighted mean over all rows for the bundle
    assert rate == pytest.approx((0.30 * 5 + 0.50 * 100) / 105)


def test_confidence_band_by_n(session: Session) -> None:
    session.add(_row("trend_70_75", "BULL", 60, 0.6))
    session.commit()
    lookup = DBCalibrationLookup(session, Settings(_env_file=None))
    assert lookup.confidence_band("trend", "BULL", "trend_70_75") == "high"
