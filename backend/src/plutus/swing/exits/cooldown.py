from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.config.settings import Settings
from plutus.db.models import AlertCooldown

CooldownKind = Literal["SL_BREACH", "SL_WARNING", "T1_HIT", "NO_PROGRESS"]


class CooldownPolicy:
    """A16 — decoupled cooldowns.

    SL_BREACH is never suppressed. Every other kind has an independent per-(symbol, kind)
    cooldown of settings.cooldown_minutes.
    """

    def __init__(self, settings: Settings) -> None:
        self._window = timedelta(minutes=settings.cooldown_minutes)

    def can_fire(
        self, symbol: str, kind: CooldownKind, now: datetime, session: Session
    ) -> bool:
        if kind == "SL_BREACH":
            return True
        last = self._last_fired(symbol, kind, session)
        if last is None:
            return True
        return (now - last) >= self._window

    def record_fired(
        self, symbol: str, kind: CooldownKind, now: datetime, session: Session
    ) -> None:
        row = self._row(symbol, kind, session)
        if row is None:
            session.add(AlertCooldown(symbol=symbol, kind=kind, last_fired_at=now))
        else:
            row.last_fired_at = now

    def _row(
        self, symbol: str, kind: CooldownKind, session: Session
    ) -> AlertCooldown | None:
        stmt = (
            select(AlertCooldown)
            .where(AlertCooldown.symbol == symbol, AlertCooldown.kind == kind)
            .order_by(AlertCooldown.last_fired_at.desc())
            .limit(1)
        )
        return session.execute(stmt).scalars().first()

    def _last_fired(
        self, symbol: str, kind: CooldownKind, session: Session
    ) -> datetime | None:
        row = self._row(symbol, kind, session)
        return row.last_fired_at if row is not None else None
