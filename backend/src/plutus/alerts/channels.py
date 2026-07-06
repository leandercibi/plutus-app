from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

AlertKind = Literal[
    "SL_BREACH",
    "SL_WARNING",
    "T1_HIT",
    "T2_HIT",
    "NO_PROGRESS",
    "ENTRY",
    "REGIME_FLIP",
    "THESIS_INVALIDATION",
    "MONDAY_REVALIDATION",
]


@dataclass(frozen=True)
class AlertMessage:
    kind: AlertKind
    symbol: str | None
    title: str
    body_md: str
    severity: Literal["INFO", "WARNING", "URGENT"]
    deduplication_key: str


@dataclass(frozen=True)
class AlertResult:
    success: bool
    channel: str
    message_id: str | None = None
    error: str | None = None


class AlertChannel(Protocol):
    name: str

    def send(self, message: AlertMessage) -> AlertResult: ...
