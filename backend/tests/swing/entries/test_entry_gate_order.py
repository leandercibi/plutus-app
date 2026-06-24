from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal
from plutus.swing.entries.gate import EntryContext, EntryDecision, EntryGate


def _signal() -> BundleSignal:
    return BundleSignal(
        symbol="INFY",
        bundle="trend",
        as_of=date(2025, 1, 1),
        entry=Decimal("100"),
        stop_loss=Decimal("95"),
        target_1=Decimal("110"),
        target_2=Decimal("120"),
    )


@dataclass
class _Spy:
    """Records call order via a shared log; configurable to allow/deny."""

    name: str
    log: list[str]
    allow: bool = True

    def check(self, signal: BundleSignal, ctx: EntryContext) -> bool:
        self.log.append(self.name)
        return self.allow


def _ctx() -> EntryContext:
    # 20 baseline days + a strong confirmation candle (2x median) so the volume gate passes
    delivery = pd.DataFrame(
        {"traded_qty": [100_000] * 20 + [200_000], "delivery_pct": [0.5] * 21}
    )
    candles = pd.DataFrame({"close": [10.0] * 21})
    return EntryContext(
        candles=candles,
        delivery=delivery,
        today_idx=20,
        earnings_in_window=False,
        atr=Decimal("2"),
        circuit_suppress=False,
        is_expiry_day=False,
    )


def test_gates_run_in_section_9_order() -> None:
    log: list[str] = []
    gate = EntryGate(
        settings=Settings(_env_file=None),
        heat=_Spy("heat", log),
        sector=_Spy("sector", log),
        corr=_Spy("corr", log),
        adv=_Spy("adv", log),
        cooldown=_Spy("cooldown", log),
    )
    decision = gate.evaluate(_signal(), _ctx())
    assert isinstance(decision, EntryDecision)
    assert decision.allowed is True
    # circuit, earnings, volume run internally (no spy), then the risk gates in order
    assert log == ["heat", "sector", "corr", "adv", "cooldown"]


def test_circuit_failure_short_circuits_before_heat() -> None:
    log: list[str] = []
    gate = EntryGate(
        settings=Settings(_env_file=None),
        heat=_Spy("heat", log),
        sector=_Spy("sector", log),
        corr=_Spy("corr", log),
        adv=_Spy("adv", log),
        cooldown=_Spy("cooldown", log),
    )
    ctx = _ctx()
    ctx = EntryContext(
        candles=ctx.candles,
        delivery=ctx.delivery,
        today_idx=ctx.today_idx,
        earnings_in_window=ctx.earnings_in_window,
        atr=ctx.atr,
        circuit_suppress=True,  # circuit gate fails
        is_expiry_day=ctx.is_expiry_day,
    )
    decision = gate.evaluate(_signal(), ctx)
    assert decision.allowed is False
    assert any("circuit" in r.lower() for r in decision.reasons)
    # no risk gate should have been consulted
    assert log == []


def test_volume_failure_short_circuits_before_heat() -> None:
    log: list[str] = []
    gate = EntryGate(
        settings=Settings(_env_file=None),
        heat=_Spy("heat", log),
        sector=_Spy("sector", log),
        corr=_Spy("corr", log),
        adv=_Spy("adv", log),
        cooldown=_Spy("cooldown", log),
    )
    ctx = _ctx()
    # weak confirmation volume -> volume gate fails
    delivery = pd.DataFrame(
        {"traded_qty": [100_000] * 20 + [100_000], "delivery_pct": [0.5] * 21}
    )
    ctx = EntryContext(
        candles=ctx.candles,
        delivery=delivery,
        today_idx=20,
        earnings_in_window=False,
        atr=Decimal("2"),
        circuit_suppress=False,
        is_expiry_day=False,
    )
    decision = gate.evaluate(_signal(), ctx)
    assert decision.allowed is False
    assert any("volume" in r.lower() for r in decision.reasons)
    assert log == []


def test_heat_failure_stops_before_remaining_risk_gates() -> None:
    log: list[str] = []
    gate = EntryGate(
        settings=Settings(_env_file=None),
        heat=_Spy("heat", log, allow=False),
        sector=_Spy("sector", log),
        corr=_Spy("corr", log),
        adv=_Spy("adv", log),
        cooldown=_Spy("cooldown", log),
    )
    decision = gate.evaluate(_signal(), _ctx())
    assert decision.allowed is False
    assert log == ["heat"]


def test_earnings_adjusts_signal_but_does_not_kill() -> None:
    log: list[str] = []
    gate = EntryGate(
        settings=Settings(_env_file=None),
        heat=_Spy("heat", log),
        sector=_Spy("sector", log),
        corr=_Spy("corr", log),
        adv=_Spy("adv", log),
        cooldown=_Spy("cooldown", log),
        earnings_policy="widen_stop",
    )
    ctx = _ctx()
    ctx = EntryContext(
        candles=ctx.candles,
        delivery=ctx.delivery,
        today_idx=ctx.today_idx,
        earnings_in_window=True,
        atr=Decimal("2"),
        circuit_suppress=False,
        is_expiry_day=False,
    )
    decision = gate.evaluate(_signal(), ctx)
    assert decision.allowed is True
    # stop widened by 1 ATR (2): 95 - 2 = 93
    assert decision.adjusted_signal.stop_loss == Decimal("93")
