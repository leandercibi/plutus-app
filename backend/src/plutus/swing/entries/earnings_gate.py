from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal

EarningsPolicy = Literal["downgrade", "widen_stop"]
EarningsAction = Literal["downgrade", "widen_stop", "pass"]


@dataclass(frozen=True)
class EarningsAdjustment:
    action: EarningsAction
    downgrade: bool
    adjusted_stop: Decimal | None
    # both options recorded for audit, independent of the chosen policy
    widen_stop_option: Decimal | None
    downgrade_option: bool


class EarningsGate:
    """B6 — when earnings fall inside the hold window the signal is not killed;
    the configured policy either downgrades one band or widens the stop by
    settings.earnings_stop_widen_atr * ATR. Both options are recorded."""

    def __init__(self, settings: Settings, policy: EarningsPolicy = "downgrade") -> None:
        self._settings = settings
        self._policy = policy

    def evaluate(
        self, signal: BundleSignal, earnings_in_window: bool, atr: Decimal
    ) -> EarningsAdjustment:
        if not earnings_in_window:
            return EarningsAdjustment(
                action="pass",
                downgrade=False,
                adjusted_stop=None,
                widen_stop_option=None,
                downgrade_option=False,
            )

        widen = Decimal(str(self._settings.earnings_stop_widen_atr)) * atr
        widened_stop = signal.stop_loss - widen

        if self._policy == "widen_stop":
            return EarningsAdjustment(
                action="widen_stop",
                downgrade=False,
                adjusted_stop=widened_stop,
                widen_stop_option=widened_stop,
                downgrade_option=True,
            )
        return EarningsAdjustment(
            action="downgrade",
            downgrade=True,
            adjusted_stop=None,
            widen_stop_option=widened_stop,
            downgrade_option=True,
        )
