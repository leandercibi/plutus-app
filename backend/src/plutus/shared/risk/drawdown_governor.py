from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.config.settings import Settings
from plutus.db.models import DrawdownGovernorState

_RECOVERY_DAYS_REQUIRED = 3


class DrawdownGovernor:
    def __init__(self, settings: Settings, session: Session) -> None:
        self._settings = settings
        self._session = session

    def _latest_state(self) -> DrawdownGovernorState | None:
        stmt = (
            select(DrawdownGovernorState).order_by(DrawdownGovernorState.as_of_date.desc()).limit(1)
        )
        return self._session.execute(stmt).scalars().first()

    def _is_drawdown_triggered(self, hwm: Decimal, pool_value: Decimal) -> bool:
        if hwm <= 0:
            return False
        drawdown = float((hwm - pool_value) / hwm)
        return drawdown >= self._settings.drawdown_governor_trigger_pct

    def current_risk_multiplier(self, pool_high_water_mark: Decimal, pool_value: Decimal) -> float:
        triggered_now = self._is_drawdown_triggered(pool_high_water_mark, pool_value)
        if triggered_now:
            return self._settings.drawdown_governor_halving_factor

        state = self._latest_state()
        if state is None:
            return 1.0
        # not in drawdown right now, but a prior governor state may still be halved
        # until the 3-day recovery rule clears it
        return state.multiplier

    def record_close(self, pool_value: Decimal, as_of: date) -> None:
        prior = self._latest_state()
        if prior is None:
            hwm = pool_value
            multiplier = 1.0
            recovery_days = 0
        else:
            hwm = max(prior.high_water_mark, pool_value)
            triggered = self._is_drawdown_triggered(hwm, pool_value)
            if triggered:
                multiplier = self._settings.drawdown_governor_halving_factor
                recovery_days = 0
            elif prior.multiplier < 1.0:
                recovery_days = prior.consecutive_recovery_days + 1
                if recovery_days >= _RECOVERY_DAYS_REQUIRED:
                    multiplier = 1.0
                    recovery_days = 0
                else:
                    multiplier = prior.multiplier
            else:
                multiplier = 1.0
                recovery_days = 0

        existing = (
            self._session.execute(
                select(DrawdownGovernorState).where(DrawdownGovernorState.as_of_date == as_of)
            )
            .scalars()
            .first()
        )
        if existing is not None:
            existing.pool_value = pool_value
            existing.high_water_mark = hwm
            existing.multiplier = multiplier
            existing.consecutive_recovery_days = recovery_days
        else:
            self._session.add(
                DrawdownGovernorState(
                    as_of_date=as_of,
                    pool_value=pool_value,
                    high_water_mark=hwm,
                    multiplier=multiplier,
                    consecutive_recovery_days=recovery_days,
                )
            )
