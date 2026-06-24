from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from plutus.db.models import CalibrationRow


def _row(
    bucket: str = "trend_score_70_75",
    sprt_state: str = "continue",
    confidence_band: str = "medium",
    ci_low_R: float = 0.1,
    expectancy_R: float = 0.4,
    ci_high_R: float = 0.7,
) -> CalibrationRow:
    return CalibrationRow(
        bucket=bucket,
        regime="BULL",
        n_closed=35,
        win_rate=0.58,
        expectancy_R=expectancy_R,
        ci_low_R=ci_low_R,
        ci_high_R=ci_high_R,
        sprt_state=sprt_state,
        last_updated=datetime(2025, 1, 1, 12, 0),
        confidence_band=confidence_band,
    )


def test_valid_row_accepted(session: Session) -> None:
    session.add(_row())
    session.commit()
    assert session.query(CalibrationRow).count() == 1


def test_ci_ordering_enforced(session: Session) -> None:
    session.add(_row(ci_low_R=0.5, expectancy_R=0.4, ci_high_R=0.7))
    with pytest.raises(IntegrityError):
        session.commit()


def test_ci_high_below_expectancy_rejected(session: Session) -> None:
    session.add(_row(ci_low_R=0.1, expectancy_R=0.4, ci_high_R=0.3))
    with pytest.raises(IntegrityError):
        session.commit()


def test_valid_sprt_states_accepted(session: Session) -> None:
    for i, state in enumerate(("accept_H0", "accept_H1", "continue")):
        session.add(_row(bucket=f"bucket_{i}", sprt_state=state))
    session.commit()
    states = {r.sprt_state for r in session.query(CalibrationRow).all()}
    assert states == {"accept_H0", "accept_H1", "continue"}


def test_invalid_sprt_state_rejected(session: Session) -> None:
    session.add(_row(sprt_state="reject"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_confidence_band_rejected(session: Session) -> None:
    session.add(_row(confidence_band="extreme"))
    with pytest.raises(IntegrityError):
        session.commit()
