from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.db.models import BundleStatPerRegime
from plutus.shared.types import BundleStats

_SHARPE_MIN = -3.0
_SHARPE_MAX = 3.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class PerRegimeStatStore:
    """B14. Persists walk-forward OOS bundle stats per (bundle, regime, as_of_date)."""

    def upsert(self, stats: BundleStats, as_of: date, session: Session) -> None:
        regime = stats.regime if stats.regime != "ALL" else "ALL"
        sharpe = _clamp(stats.sharpe_raw, _SHARPE_MIN, _SHARPE_MAX)
        existing = session.execute(
            select(BundleStatPerRegime).where(
                BundleStatPerRegime.bundle == stats.bundle,
                BundleStatPerRegime.regime == regime,
                BundleStatPerRegime.as_of_date == as_of,
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                BundleStatPerRegime(
                    bundle=stats.bundle,
                    regime=regime,
                    as_of_date=as_of,
                    oos_sharpe_shrunk=sharpe,
                    oos_expectancy_R=stats.expectancy_R,
                    n_trades=stats.n_trades,
                    ci_low=stats.ci_low_R,
                    ci_high=stats.ci_high_R,
                )
            )
        else:
            existing.oos_sharpe_shrunk = sharpe
            existing.oos_expectancy_R = stats.expectancy_R
            existing.n_trades = stats.n_trades
            existing.ci_low = stats.ci_low_R
            existing.ci_high = stats.ci_high_R

    def latest(self, bundle: str, regime: str, session: Session) -> BundleStatPerRegime | None:
        return session.execute(
            select(BundleStatPerRegime)
            .where(
                BundleStatPerRegime.bundle == bundle,
                BundleStatPerRegime.regime == regime,
            )
            .order_by(BundleStatPerRegime.as_of_date.desc())
            .limit(1)
        ).scalar_one_or_none()
