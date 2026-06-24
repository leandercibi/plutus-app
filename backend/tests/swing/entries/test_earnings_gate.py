from __future__ import annotations

from datetime import date
from decimal import Decimal

from plutus.config.settings import Settings
from plutus.shared.types import BundleSignal
from plutus.swing.entries.earnings_gate import EarningsAdjustment, EarningsGate


def _signal(stop: str = "95") -> BundleSignal:
    return BundleSignal(
        symbol="INFY",
        bundle="trend",
        as_of=date(2025, 1, 1),
        entry=Decimal("100"),
        stop_loss=Decimal(stop),
        target_1=Decimal("110"),
        target_2=Decimal("120"),
    )


def test_earnings_outside_window_passes() -> None:
    gate = EarningsGate(Settings(_env_file=None))
    adj = gate.evaluate(_signal(), earnings_in_window=False, atr=Decimal("2"))
    assert isinstance(adj, EarningsAdjustment)
    assert adj.action == "pass"
    assert adj.downgrade is False
    assert adj.adjusted_stop is None


def test_earnings_inside_window_widen_stop_policy() -> None:
    gate = EarningsGate(Settings(_env_file=None), policy="widen_stop")
    atr = Decimal("2")
    adj = gate.evaluate(_signal(stop="95"), earnings_in_window=True, atr=atr)
    assert adj.action == "widen_stop"
    # widened by settings.earnings_stop_widen_atr (1.0) * atr (2) = 2 -> 95 - 2 = 93
    assert adj.adjusted_stop == Decimal("93")
    assert adj.downgrade is False


def test_earnings_inside_window_downgrade_policy() -> None:
    gate = EarningsGate(Settings(_env_file=None), policy="downgrade")
    adj = gate.evaluate(_signal(), earnings_in_window=True, atr=Decimal("2"))
    assert adj.action == "downgrade"
    assert adj.downgrade is True
    assert adj.adjusted_stop is None


def test_both_options_recorded_in_adjustment() -> None:
    gate = EarningsGate(Settings(_env_file=None), policy="widen_stop")
    adj = gate.evaluate(_signal(stop="95"), earnings_in_window=True, atr=Decimal("2"))
    # both options available for audit regardless of chosen policy
    assert adj.widen_stop_option == Decimal("93")
    assert adj.downgrade_option is True
