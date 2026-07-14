from __future__ import annotations

import pandas as pd
import pytest

from plutus.accumulation.fundamentals.valuation import Valuation, ValuationInputs


def _history(eps_by_year: list[tuple[int, float]]) -> pd.DataFrame:
    return pd.DataFrame(eps_by_year, columns=["year", "eps"])


@pytest.fixture
def valuation() -> Valuation:
    return Valuation()


def test_normalized_eps_excludes_negative_years(valuation: Valuation) -> None:
    history = _history([(2020, 10.0), (2021, -4.0), (2022, 12.0), (2023, 14.0), (2024, 16.0)])
    # negative 2021 excluded -> mean of [10, 12, 14, 16] = 13.0
    assert valuation.normalized_eps(history) == pytest.approx(13.0)


def test_normalized_eps_all_positive(valuation: Valuation) -> None:
    history = _history([(2020, 10.0), (2021, 12.0), (2022, 14.0), (2023, 16.0), (2024, 18.0)])
    assert valuation.normalized_eps(history) == pytest.approx(14.0)


def test_cagr_eps_insufficient_history_returns_none(valuation: Valuation) -> None:
    history = _history([(2023, 10.0), (2024, 12.0)])
    assert valuation.cagr_eps(history, years=5) is None


def test_cagr_eps_negative_endpoint_returns_none(valuation: Valuation) -> None:
    history = _history([(2020, 10.0), (2021, 12.0), (2022, 14.0), (2023, 16.0), (2024, -2.0)])
    assert valuation.cagr_eps(history, years=5) is None


def test_cagr_eps_strong_growth(valuation: Valuation) -> None:
    # 10 -> 20 over 4 intervals => (20/10)^(1/4)-1 ~ 0.1892
    history = _history([(2020, 10.0), (2021, 12.0), (2022, 14.0), (2023, 17.0), (2024, 20.0)])
    cagr = valuation.cagr_eps(history, years=5)
    assert cagr is not None
    assert cagr == pytest.approx((20.0 / 10.0) ** (1 / 4) - 1, abs=1e-4)


def test_value_trap_cheap_pe_but_negative_cagr_scores_low(
    valuation: Valuation,
) -> None:
    # screaming cheap PE but earnings declining -> value trap -> low score
    history = _history([(2020, 20.0), (2021, 18.0), (2022, 15.0), (2023, 12.0), (2024, 10.0)])
    trap = ValuationInputs(
        pe_ttm=6.0, pe_5y_median=18.0, ev_ebitda=4.0, earnings_history_5y=history
    )
    quality_value = ValuationInputs(
        pe_ttm=14.0,
        pe_5y_median=18.0,
        ev_ebitda=10.0,
        earnings_history_5y=_history(
            [(2020, 10.0), (2021, 12.0), (2022, 14.0), (2023, 17.0), (2024, 20.0)]
        ),
    )
    assert valuation.score(trap) < valuation.score(quality_value)


def test_cheap_pe_with_strong_cagr_scores_high(valuation: Valuation) -> None:
    history = _history([(2020, 10.0), (2021, 12.0), (2022, 14.0), (2023, 17.0), (2024, 20.0)])
    inputs = ValuationInputs(
        pe_ttm=10.0, pe_5y_median=20.0, ev_ebitda=8.0, earnings_history_5y=history
    )
    assert valuation.score(inputs) >= 20
