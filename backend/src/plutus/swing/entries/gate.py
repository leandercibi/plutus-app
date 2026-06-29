from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal
from plutus.swing.entries.earnings_gate import EarningsGate, EarningsPolicy
from plutus.swing.entries.volume_gate import VolumeGate


@dataclass(frozen=True)
class EntryContext:
    candles: pd.DataFrame
    delivery: pd.DataFrame
    today_idx: int
    earnings_in_window: bool
    atr: Decimal
    circuit_suppress: bool
    is_expiry_day: bool


@dataclass(frozen=True)
class EntryDecision:
    allowed: bool
    reasons: tuple[str, ...]
    adjusted_signal: BundleSignal


class RiskGate(Protocol):
    def check(self, signal: BundleSignal, ctx: EntryContext) -> bool: ...


class EntryGate:
    """Composes the swing entry gates in the binding §9 order:

    1. CircuitGate (B7)  2. EarningsGate (B6, adjust not kill)  3. VolumeGate (A9)
    4. PortfolioHeat  5. SectorCap  6. CorrelationGuard  7. ADVCap  8. Cooldown.

    The four shared risk gates plus cooldown are passed in as already-constructed
    objects exposing .check(signal, ctx) -> bool. The first failing gate
    short-circuits the rest.
    """

    def __init__(
        self,
        settings: Settings,
        heat: RiskGate,
        sector: RiskGate,
        corr: RiskGate,
        adv: RiskGate,
        cooldown: RiskGate,
        earnings_policy: EarningsPolicy = "downgrade",
    ) -> None:
        self._settings = settings
        self._volume = VolumeGate(settings)
        self._earnings = EarningsGate(settings, policy=earnings_policy)
        self._risk_gates: list[tuple[str, RiskGate]] = [
            ("heat", heat),
            ("sector", sector),
            ("corr", corr),
            ("adv", adv),
            ("cooldown", cooldown),
        ]

    def evaluate(self, signal: BundleSignal, ctx: EntryContext) -> EntryDecision:
        reasons: list[str] = []

        # 1. Circuit (B7)
        if ctx.circuit_suppress:
            return EntryDecision(
                allowed=False,
                reasons=("circuit band recently hit; setup suppressed",),
                adjusted_signal=signal,
            )

        # 2. Earnings (B6) — adjusts, never kills
        adjusted = signal
        earnings_adj = self._earnings.evaluate(signal, ctx.earnings_in_window, ctx.atr)
        if (
            earnings_adj.action == "widen_stop"
            and earnings_adj.adjusted_stop is not None
        ):
            adjusted = dataclasses.replace(signal, stop_loss=earnings_adj.adjusted_stop)
            reasons.append("earnings in window: stop widened 1 ATR")
        elif earnings_adj.action == "downgrade":
            reasons.append("earnings in window: signal downgraded one band")

        # 3. Volume (A9)
        if not self._volume.passes(
            ctx.candles, ctx.delivery, ctx.today_idx, is_expiry_day=ctx.is_expiry_day
        ):
            return EntryDecision(
                allowed=False,
                reasons=(
                    *reasons,
                    "delivery-adjusted volume below confirmation threshold",
                ),
                adjusted_signal=adjusted,
            )

        # 4-8. Shared risk gates + cooldown, in order
        for name, gate in self._risk_gates:
            if not gate.check(adjusted, ctx):
                return EntryDecision(
                    allowed=False,
                    reasons=(*reasons, f"{name} gate rejected entry"),
                    adjusted_signal=adjusted,
                )

        return EntryDecision(
            allowed=True, reasons=tuple(reasons), adjusted_signal=adjusted
        )
