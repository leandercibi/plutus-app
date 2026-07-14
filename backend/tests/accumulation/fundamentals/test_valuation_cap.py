from __future__ import annotations

import pandas as pd
import pytest

from plutus.accumulation.fundamentals.valuation import Valuation, ValuationInputs


def _history(eps_by_year: list[tuple[int, float]]) -> pd.DataFrame:
    return pd.DataFrame(eps_by_year, columns=["year", "eps"])


@pytest.mark.hallmark
def test_valuation_cap_no_inputs_exceed_30() -> None:
    """A12 hallmark: a screaming-cheap value trap (or any input combo) cannot score > 30."""
    valuation = Valuation()
    # extreme cheap, extreme growth, extreme everything
    extreme_growth = _history([(2020, 1.0), (2021, 5.0), (2022, 20.0), (2023, 60.0), (2024, 200.0)])
    extreme_cases = [
        ValuationInputs(
            pe_ttm=0.5,
            pe_5y_median=1000.0,
            ev_ebitda=0.1,
            earnings_history_5y=extreme_growth,
        ),
        ValuationInputs(
            pe_ttm=1.0,
            pe_5y_median=500.0,
            ev_ebitda=1.0,
            earnings_history_5y=extreme_growth,
        ),
        ValuationInputs(
            pe_ttm=2.0,
            pe_5y_median=100.0,
            ev_ebitda=2.0,
            earnings_history_5y=_history(
                [(2020, 5.0), (2021, 8.0), (2022, 13.0), (2023, 21.0), (2024, 34.0)]
            ),
        ),
    ]
    for inputs in extreme_cases:
        assert valuation.score(inputs) <= 30
        assert valuation.score(inputs) >= 0
