from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from plutus.alerts.channels import AlertChannel, AlertMessage, AlertResult
from plutus.swing.exits.cooldown import CooldownKind, CooldownPolicy


class AlertMonitor:
    """Ties exit/entry events to channels, honoring decoupled cooldowns (A16)."""

    def __init__(self, channels: list[AlertChannel], cooldown: CooldownPolicy) -> None:
        self._channels = channels
        self._cooldown = cooldown

    def emit(
        self, message: AlertMessage, now: datetime, session: Session
    ) -> list[AlertResult]:
        kind = message.kind
        if _is_cooldown_kind(kind) and message.symbol is not None:
            cooldown_kind: CooldownKind = kind  # type: ignore[assignment]
            if not self._cooldown.can_fire(message.symbol, cooldown_kind, now, session):
                return []
            results = [c.send(message) for c in self._channels]
            self._cooldown.record_fired(message.symbol, cooldown_kind, now, session)
            return results
        return [c.send(message) for c in self._channels]


def _is_cooldown_kind(kind: str) -> bool:
    return kind in {"SL_BREACH", "SL_WARNING", "T1_HIT", "NO_PROGRESS"}
