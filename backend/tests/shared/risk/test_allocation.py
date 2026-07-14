from __future__ import annotations

from decimal import Decimal

import pytest

from plutus.config.settings import Settings
from plutus.shared.regime.detector import RegimeVerdict
from plutus.shared.risk.allocation import Allocation


def _regime(label: str) -> RegimeVerdict:
    return RegimeVerdict(label=label, confidence="high", reasons=[], breadth_confirmed=True)  # type: ignore[arg-type]


@pytest.fixture
def alloc() -> Allocation:
    return Allocation(Settings(_env_file=None))


def test_bull_desires_70pct_swing(alloc: Allocation) -> None:
    assert alloc.desired_swing_pct(_regime("BULL")) == pytest.approx(0.7)


def test_sideways_desires_50pct_swing(alloc: Allocation) -> None:
    assert alloc.desired_swing_pct(_regime("SIDEWAYS")) == pytest.approx(0.5)


def test_bear_desires_30pct_swing(alloc: Allocation) -> None:
    assert alloc.desired_swing_pct(_regime("BEAR")) == pytest.approx(0.3)


def test_committed_capital_never_moved(alloc: Allocation) -> None:
    total = Decimal("1000000")
    committed_swing = Decimal("400000")
    committed_accum = Decimal("300000")
    plan = alloc.reallocate_uncommitted(total, committed_swing, committed_accum, _regime("BULL"))
    # committed amounts are preserved exactly
    assert plan.committed_swing == committed_swing
    assert plan.committed_accumulation == committed_accum
    # only the uncommitted 300000 is retilted
    assert plan.uncommitted == Decimal("300000")
    assert plan.target_swing >= committed_swing
