from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from plutus.backtesting.per_regime import PerRegimeStatStore
from plutus.db.models import BundleStatPerRegime
from plutus.shared.types import BundleStats


def _stats(
    bundle: str = "trend", regime: str = "BULL", exp: float = 0.4
) -> BundleStats:
    return BundleStats(
        bundle=bundle,
        regime=regime,
        n_trades=50,
        win_rate=0.55,
        expectancy_R=exp,
        sharpe_raw=1.2,
        ci_low_R=0.2,
        ci_high_R=0.6,
    )


def test_upsert_inserts_row(session: Session) -> None:
    store = PerRegimeStatStore()
    store.upsert(_stats(), as_of=date(2020, 1, 1), session=session)
    session.commit()
    rows = session.query(BundleStatPerRegime).all()
    assert len(rows) == 1
    assert rows[0].bundle == "trend"
    assert rows[0].oos_expectancy_R == 0.4


def test_upsert_idempotent_on_key(session: Session) -> None:
    store = PerRegimeStatStore()
    store.upsert(_stats(exp=0.4), as_of=date(2020, 1, 1), session=session)
    session.commit()
    # Same (bundle, regime, as_of_date) -> update, not duplicate.
    store.upsert(_stats(exp=0.9), as_of=date(2020, 1, 1), session=session)
    session.commit()
    rows = session.query(BundleStatPerRegime).all()
    assert len(rows) == 1
    assert rows[0].oos_expectancy_R == 0.9


def test_different_as_of_creates_new_row(session: Session) -> None:
    store = PerRegimeStatStore()
    store.upsert(_stats(), as_of=date(2020, 1, 1), session=session)
    store.upsert(_stats(), as_of=date(2020, 2, 1), session=session)
    session.commit()
    assert session.query(BundleStatPerRegime).count() == 2


def test_latest_returns_most_recent(session: Session) -> None:
    store = PerRegimeStatStore()
    store.upsert(_stats(exp=0.1), as_of=date(2020, 1, 1), session=session)
    store.upsert(_stats(exp=0.7), as_of=date(2020, 3, 1), session=session)
    session.commit()
    latest = store.latest("trend", "BULL", session)
    assert latest is not None
    assert latest.as_of_date == date(2020, 3, 1)
    assert latest.oos_expectancy_R == 0.7


def test_latest_none_when_absent(session: Session) -> None:
    store = PerRegimeStatStore()
    assert store.latest("missing", "BULL", session) is None


def test_sharpe_clamped_to_range(session: Session) -> None:
    store = PerRegimeStatStore()
    hot = BundleStats(
        bundle="trend",
        regime="BULL",
        n_trades=50,
        win_rate=0.9,
        expectancy_R=2.0,
        sharpe_raw=9.9,
        ci_low_R=1.0,
        ci_high_R=3.0,
    )
    store.upsert(hot, as_of=date(2020, 1, 1), session=session)
    session.commit()
    row = session.query(BundleStatPerRegime).one()
    assert -3.0 <= row.oos_sharpe_shrunk <= 3.0
