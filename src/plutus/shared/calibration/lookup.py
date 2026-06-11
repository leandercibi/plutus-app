from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.config.settings import Settings
from plutus.db.models import CalibrationRow
from plutus.shared.calibration.protocol import HitField


class DBCalibrationLookup:
    """Read path over db.CalibrationRow for scorers (A4/A5). Falls back to a
    cross-regime pooled rate when the (bundle, regime) sample is below the floor."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def get(self, bundle: str, regime: str, score_bucket: str) -> CalibrationRow | None:
        stmt = select(CalibrationRow).where(
            CalibrationRow.bucket == score_bucket,
            CalibrationRow.regime == regime,
        )
        return self._session.execute(stmt).scalars().first()

    def n_for(self, bundle: str, regime: str) -> int:
        stmt = select(CalibrationRow).where(
            CalibrationRow.bucket.like(f"{bundle}%"),
            CalibrationRow.regime == regime,
        )
        rows = self._session.execute(stmt).scalars().all()
        return sum(r.n_closed for r in rows)

    def hit_rate(self, bundle: str, regime: str, target_field: HitField) -> float:
        if self.n_for(bundle, regime) >= self._settings.calibration_min_n_low:
            row = self._best_row(bundle, regime)
            if row is not None:
                return row.win_rate
        # fallback: cross-regime pooled win rate for the bundle
        stmt = select(CalibrationRow).where(CalibrationRow.bucket.like(f"{bundle}%"))
        rows = self._session.execute(stmt).scalars().all()
        if not rows:
            return 0.0
        total_n = sum(r.n_closed for r in rows)
        if total_n == 0:
            return 0.0
        return sum(r.win_rate * r.n_closed for r in rows) / total_n

    def confidence_band(
        self, bundle: str, regime: str, score_bucket: str
    ) -> Literal["low", "medium", "high"]:
        n = self.n_for(bundle, regime)
        if n < self._settings.calibration_min_n_low:
            return "low"
        if n < self._settings.calibration_min_n_high:
            return "medium"
        return "high"

    def _best_row(self, bundle: str, regime: str) -> CalibrationRow | None:
        stmt = (
            select(CalibrationRow)
            .where(
                CalibrationRow.bucket.like(f"{bundle}%"),
                CalibrationRow.regime == regime,
            )
            .order_by(CalibrationRow.n_closed.desc())
        )
        return self._session.execute(stmt).scalars().first()
