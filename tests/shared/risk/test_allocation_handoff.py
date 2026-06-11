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


def test_regime_flip_to_bull_preserves_accumulation_tranches(alloc: Allocation) -> None:
    # accumulation has committed (filled) tranches; a BULL flip must not force-migrate them
    total = Decimal("1000000")
    committed_swing = Decimal("200000")
    committed_accumulation = Decimal("500000")  # filled tranches
    plan = alloc.reallocate_uncommitted(
        total, committed_swing, committed_accumulation, _regime("BULL")
    )
    # filled accumulation tranches are untouched
    assert plan.committed_accumulation == committed_accumulation
    # only the 300000 uncommitted moves; accumulation commitment is never reduced
    assert plan.target_accumulation >= committed_accumulation
