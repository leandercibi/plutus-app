from __future__ import annotations

import pandas as pd
import pytest

from plutus.config.settings import Settings
from plutus.shared.risk.correlation_guard import CorrelationGuard
from plutus.shared.risk.types import OpenPosition


class _Proposed:
    def __init__(self, symbol: str, sector: str = "IT", risk_R: float = 1.0) -> None:
        self.symbol = symbol
        self.sector = sector
        self.risk_R = risk_R


@pytest.fixture
def guard() -> CorrelationGuard:
    return CorrelationGuard(Settings(_env_file=None))


def _returns(corr_ab: float) -> pd.DataFrame:
    # build a 60-row returns frame for A and B with target correlation
    import numpy as np

    rng = np.random.default_rng(7)
    base = rng.normal(0, 1, 60)
    noise = rng.normal(0, 1, 60)
    a = base
    b = corr_ab * base + (1 - abs(corr_ab)) * noise
    return pd.DataFrame({"A": a, "B": b})


def test_highly_correlated_rejected(guard: CorrelationGuard) -> None:
    positions = [OpenPosition("A", "IT", 1.0)]
    proposed = _Proposed("B")
    returns = _returns(0.95)
    decision = guard.check(positions, proposed, returns)
    assert decision.allowed is False
    assert decision.reasons


def test_inverse_correlated_allowed(guard: CorrelationGuard) -> None:
    positions = [OpenPosition("A", "IT", 1.0)]
    proposed = _Proposed("B")
    returns = _returns(-0.9)
    decision = guard.check(positions, proposed, returns)
    assert decision.allowed is True


def test_no_open_positions_allowed(guard: CorrelationGuard) -> None:
    decision = guard.check([], _Proposed("B"), _returns(0.95))
    assert decision.allowed is True
