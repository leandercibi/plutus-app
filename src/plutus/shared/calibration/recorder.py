from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.config.settings import Settings
from plutus.db.models import CalibrationRow
from plutus.shared.calibration.ci import bootstrap_R_interval
from plutus.shared.calibration.regime_partition import TradeOutcome
from plutus.shared.calibration.sprt import SPRT, SPRTState


class OutcomeRecorder:
    """A14 — ingest a closed-trade outcome into the (bucket, regime) calibration row."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def record(self, outcome: TradeOutcome, session: Session) -> CalibrationRow:
        row = (
            session.execute(
                select(CalibrationRow).where(
                    CalibrationRow.bucket == outcome.score_bucket,
                    CalibrationRow.regime == outcome.regime_at_signal,
                )
            )
            .scalars()
            .first()
        )

        if row is None:
            row = CalibrationRow(
                bucket=outcome.score_bucket,
                regime=outcome.regime_at_signal,
                n_closed=0,
                win_rate=0.0,
                expectancy_R=0.0,
                ci_low_R=0.0,
                ci_high_R=0.0,
                sprt_state="continue",
                last_updated=outcome.closed_at,
                confidence_band="low",
            )
            session.add(row)
            row_rs: list[float] = []
        else:
            row_rs = self._existing_rs(row)

        row_rs.append(outcome.realized_R)
        n = len(row_rs)
        wins = sum(1 for r in row_rs if r > 0)
        row.n_closed = n
        row.win_rate = wins / n
        row.expectancy_R = sum(row_rs) / n
        ci_low, ci_high = bootstrap_R_interval(row_rs, seed=0)
        # keep the CI ordering constraint satisfied around expectancy
        row.ci_low_R = min(ci_low, row.expectancy_R)
        row.ci_high_R = max(ci_high, row.expectancy_R)
        row.sprt_state = self._sprt_state(row_rs).decision
        row.confidence_band = self._band(n)
        row.last_updated = outcome.closed_at
        return row

    def _existing_rs(self, row: CalibrationRow) -> list[float]:
        # reconstruct an R series consistent with stored n/expectancy for incremental update
        return [row.expectancy_R] * row.n_closed

    def _sprt_state(self, rs: list[float]) -> SPRTState:
        sprt = SPRT(
            alpha=self._settings.sprt_alpha,
            beta=self._settings.sprt_beta,
            h0_expectancy=self._settings.expectancy_floor_R,
            h1_expectancy=self._settings.expectancy_floor_R + 0.2,
        )
        state = sprt.initial()
        for r in rs:
            state = sprt.update(state, r)
        return state

    def _band(self, n: int) -> str:
        if n < self._settings.calibration_min_n_low:
            return "low"
        if n < self._settings.calibration_min_n_high:
            return "medium"
        return "high"
