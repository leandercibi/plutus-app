from __future__ import annotations

from decimal import Decimal

import pytest

from plutus.config.settings import Settings
from plutus.shared.risk.cash_position import CashAsPosition


class _Signal:
    def __init__(self, expectancy_R: float) -> None:
        self.expectancy_R = expectancy_R


@pytest.fixture
def cash() -> CashAsPosition:
    return CashAsPosition(Settings(_env_file=None))


def test_one_signal_below_min_deploys_one_with_banner(cash: CashAsPosition) -> None:
    signals = [_Signal(0.5)]
    decision = cash.decide(signals, Decimal("1000000"))
    assert decision.deploy_count == 1
    assert decision.cash_pct_of_pool > 0
    assert decision.reason == (
        "market offered 1 qualifying setups; "
        f"{decision.cash_pct_of_pool:.0%} of swing pool held in cash."
    )


def test_five_signals_deploys_all_no_cash_banner(cash: CashAsPosition) -> None:
    signals = [_Signal(0.5) for _ in range(5)]
    decision = cash.decide(signals, Decimal("1000000"))
    assert decision.deploy_count == 5
    assert decision.cash_pct_of_pool == 0.0


def test_deploys_top_by_expectancy_when_below_min(cash: CashAsPosition) -> None:
    # 2 signals at min=3 -> deploy both (less than min means deploy what we have,
    # remainder of the min slots stays cash)
    signals = [_Signal(0.2), _Signal(0.9)]
    decision = cash.decide(signals, Decimal("1000000"))
    assert decision.deploy_count == 2
