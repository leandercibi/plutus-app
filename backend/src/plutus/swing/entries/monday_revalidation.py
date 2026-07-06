from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal


@dataclass(frozen=True)
class RevalidationOutcome:
    keep: bool
    reason: str


class MondayRevalidation:
    """A15 — re-validate a Sunday signal against Monday's open.

    A weekend gap greater than settings.monday_gap_kill_atr_mult * ATR invalidates
    the plan (it was drawn for the old entry). A corroborated weekend hard-kill also
    kills. Otherwise the signal is kept.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def reevaluate(
        self,
        sunday_signal: BundleSignal,
        monday_open: Decimal,
        atr: Decimal,
        hard_kill_fires: bool,
    ) -> RevalidationOutcome:
        if hard_kill_fires:
            return RevalidationOutcome(keep=False, reason="weekend sentiment hard-kill fired")

        gap = abs(monday_open - sunday_signal.entry)
        gap_limit = Decimal(str(self._settings.monday_gap_kill_atr_mult)) * atr
        if gap > gap_limit:
            return RevalidationOutcome(
                keep=False,
                reason=f"weekend gap {gap} exceeds {gap_limit} ({self._settings.monday_gap_kill_atr_mult} ATR)",
            )

        return RevalidationOutcome(keep=True, reason="clean monday open")
