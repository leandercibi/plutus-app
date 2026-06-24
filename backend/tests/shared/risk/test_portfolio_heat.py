from __future__ import annotations

import pandas as pd
import pytest

from plutus.config.settings import Settings
from plutus.shared.risk.portfolio_heat import HeatInputs, PortfolioHeat
from plutus.shared.risk.types import OpenPosition


class _Proposed:
    def __init__(self, symbol: str, sector: str, risk_R: float) -> None:
        self.symbol = symbol
        self.sector = sector
        self.risk_R = risk_R


@pytest.fixture
def heat() -> PortfolioHeat:
    return PortfolioHeat(Settings(_env_file=None))


def _zero_corr(symbols: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(0.0, index=symbols, columns=symbols)
    for s in symbols:
        df.loc[s, s] = 1.0
    return df


def test_heat_without_correlation_is_sum_of_risks(heat: PortfolioHeat) -> None:
    positions = [
        OpenPosition("A", "IT", 1.0),
        OpenPosition("B", "BANK", 1.0),
    ]
    proposed = _Proposed("C", "PHARMA", 1.0)
    corr = _zero_corr(["A", "B", "C"])
    decision = heat.evaluate(HeatInputs(positions, proposed, corr))
    assert decision.current_heat_R == pytest.approx(2.0)
    assert decision.projected_heat_R == pytest.approx(3.0)
    assert decision.allowed is True


def test_high_correlation_increases_effective_heat(heat: PortfolioHeat) -> None:
    positions = [
        OpenPosition("A", "IT", 1.0),
        OpenPosition("B", "IT", 1.0),
    ]
    proposed = _Proposed("C", "IT", 1.0)
    corr = _zero_corr(["A", "B", "C"])
    for i in ("A", "B", "C"):
        for j in ("A", "B", "C"):
            if i != j:
                corr.loc[i, j] = 0.8
    decision = heat.evaluate(HeatInputs(positions, proposed, corr))
    # With 0.8 mean correlation, effective heat well above the naive 3.0
    assert decision.projected_heat_R > 3.0


def test_allowed_flips_false_at_cap() -> None:
    settings = Settings(_env_file=None, max_portfolio_heat_R=2.5)
    heat = PortfolioHeat(settings)
    positions = [
        OpenPosition("A", "IT", 1.0),
        OpenPosition("B", "IT", 1.0),
    ]
    proposed = _Proposed("C", "IT", 1.0)
    corr = _zero_corr(["A", "B", "C"])
    for i in ("A", "B", "C"):
        for j in ("A", "B", "C"):
            if i != j:
                corr.loc[i, j] = 0.8
    decision = heat.evaluate(HeatInputs(positions, proposed, corr))
    assert decision.allowed is False
    assert decision.reasons
