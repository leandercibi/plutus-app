from __future__ import annotations

import pandas as pd
import pytest

from plutus.accumulation.fundamentals.valuation import Valuation


def _history(eps_by_year: list[tuple[int, float]]) -> pd.DataFrame:
    return pd.DataFrame(eps_by_year, columns=["year", "eps"])


@pytest.mark.hallmark
def test_growth_score_uses_cagr_not_yoy() -> None:
    """A12 hallmark: a +120% YoY recovery spike must NOT spike the growth score.

    A base-effect recovery (flat-ish multi-year, one big YoY jump) should score
    well below a stock that compounds steadily — because growth_score uses 3y/5y
    CAGR, not the latest YoY change.
    """
    valuation = Valuation()

    # base-effect: ~flat then a recovery year +120% YoY (10 -> 22)
    base_effect = _history([(2020, 10.0), (2021, 9.0), (2022, 9.5), (2023, 10.0), (2024, 22.0)])
    # steady compounder: clean 3y/5y CAGR, no single spike
    steady = _history([(2020, 10.0), (2021, 13.0), (2022, 17.0), (2023, 22.0), (2024, 29.0)])

    spike_yoy = (22.0 - 10.0) / 10.0
    assert spike_yoy == pytest.approx(1.2)  # +120% latest YoY

    base_score = valuation.growth_score(base_effect)
    steady_score = valuation.growth_score(steady)

    # the steady compounder must outscore the base-effect spike
    assert steady_score > base_score
    # and the base-effect score must be moderate, not maxed by the +120% spike
    assert base_score <= 15
    assert steady_score <= 25
