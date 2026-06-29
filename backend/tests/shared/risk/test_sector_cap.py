from __future__ import annotations

from decimal import Decimal

import pytest

from plutus.config.settings import Settings
from plutus.shared.risk.sector_cap import SectorCap
from plutus.shared.risk.types import OpenPosition


class _Proposed:
    def __init__(self, symbol: str, sector: str, risk_R: float = 1.0) -> None:
        self.symbol = symbol
        self.sector = sector
        self.risk_R = risk_R


@pytest.fixture
def cap() -> SectorCap:
    return SectorCap(Settings(_env_file=None))


def test_exceeding_count_cap_rejected(cap: SectorCap) -> None:
    # default sector_cap_count = 3; three IT already open, proposed IT is the 4th
    positions = [
        OpenPosition("A", "IT", 1.0),
        OpenPosition("B", "IT", 1.0),
        OpenPosition("C", "IT", 1.0),
    ]
    decision = cap.check(positions, _Proposed("D", "IT"), Decimal("100000000"))
    assert decision.allowed is False
    assert decision.reasons


def test_diversified_portfolio_allowed(cap: SectorCap) -> None:
    positions = [
        OpenPosition("A", "IT", 1.0),
        OpenPosition("B", "BANK", 1.0),
        OpenPosition("C", "PHARMA", 1.0),
    ]
    decision = cap.check(positions, _Proposed("D", "AUTO"), Decimal("100000000"))
    assert decision.allowed is True


def test_within_count_cap_allowed(cap: SectorCap) -> None:
    positions = [
        OpenPosition("A", "IT", 1.0),
        OpenPosition("B", "IT", 1.0),
    ]
    # proposed makes 3 IT positions == cap of 3, still allowed
    decision = cap.check(positions, _Proposed("C", "IT"), Decimal("100000000"))
    assert decision.allowed is True


def test_exceeding_pct_cap_rejected(cap: SectorCap) -> None:
    # default sector_cap_pct_of_pool = 0.30; one IT position already at 25% of pool,
    # proposed adds another 10% -> 35% of pool > 30% cap.
    pool = Decimal("100000000")
    positions = [OpenPosition("A", "IT", 1.0, position_value_inr=25_000_000.0)]
    proposed = _Proposed("B", "IT")
    decision = cap.check(positions, proposed, pool, proposed_value_inr=10_000_000.0)
    assert decision.allowed is False
    assert any("exposure" in r for r in decision.reasons)
