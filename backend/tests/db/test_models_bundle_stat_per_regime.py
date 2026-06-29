from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from plutus.db.models import BundleStatPerRegime


def _row(
    bundle: str = "trend",
    regime: str = "BULL",
    d: date = date(2025, 1, 1),
    sharpe: float = 1.2,
) -> BundleStatPerRegime:
    return BundleStatPerRegime(
        bundle=bundle,
        regime=regime,
        as_of_date=d,
        oos_sharpe_shrunk=sharpe,
        oos_expectancy_R=0.4,
        n_trades=50,
        ci_low=0.2,
        ci_high=0.6,
    )


def test_unique_bundle_regime_as_of_date(session: Session) -> None:
    session.add(_row())
    session.commit()
    session.add(_row())
    with pytest.raises(IntegrityError):
        session.commit()


def test_different_regime_same_bundle_date_allowed(session: Session) -> None:
    session.add(_row(regime="BULL"))
    session.add(_row(regime="BEAR"))
    session.commit()
    assert session.query(BundleStatPerRegime).count() == 2


def test_shrunk_sharpe_above_range_rejected(session: Session) -> None:
    session.add(_row(sharpe=3.5))
    with pytest.raises(IntegrityError):
        session.commit()


def test_shrunk_sharpe_below_range_rejected(session: Session) -> None:
    session.add(_row(sharpe=-3.5))
    with pytest.raises(IntegrityError):
        session.commit()
