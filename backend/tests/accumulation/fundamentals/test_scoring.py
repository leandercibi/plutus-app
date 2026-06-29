from __future__ import annotations

import pandas as pd
import pytest

from plutus.accumulation.fundamentals.hard_avoid import FundamentalsSnapshot
from plutus.accumulation.fundamentals.scoring import FundamentalsScorer
from plutus.accumulation.fundamentals.valuation import ValuationInputs
from plutus.accumulation.rs.blend import RSBlendResult
from plutus.config.settings import Settings


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        [(2020, 10.0), (2021, 13.0), (2022, 17.0), (2023, 22.0), (2024, 29.0)],
        columns=["year", "eps"],
    )


def _snapshot(**overrides: object) -> FundamentalsSnapshot:
    base: dict[str, object] = {
        "de": 0.3,
        "is_financial": False,
        "last_eps_yoy_change": 0.20,
        "improving_guidance": True,
        "going_concern_flag": False,
        "promoter_pledge_increase_pp": 0.0,
        "roce": 0.30,
        "fcf_margin": 0.22,
        "pe_ttm": 14.0,
    }
    base.update(overrides)
    return FundamentalsSnapshot(**base)  # type: ignore[arg-type]


@pytest.fixture
def scorer() -> FundamentalsScorer:
    return FundamentalsScorer(Settings(_env_file=None))


def test_high_quality_compounder_scores_well(scorer: FundamentalsScorer) -> None:
    result = scorer.score(
        snapshot=_snapshot(),
        valuation_inputs=ValuationInputs(
            pe_ttm=14.0, pe_5y_median=20.0, ev_ebitda=8.0, earnings_history_5y=_history()
        ),
        earnings_history=_history(),
        rs_blend=RSBlendResult(rs_30=0.08, rs_90=0.12, rs_180=0.15, blended=0.12),
    )
    assert result.pillars.total <= 100
    assert result.hard_avoid.avoid is False
    assert result.label in {"ACCUMULATE_NOW", "BUILD_SLOWLY"}


def test_hard_avoid_forces_avoid_label(scorer: FundamentalsScorer) -> None:
    result = scorer.score(
        snapshot=_snapshot(going_concern_flag=True),
        valuation_inputs=ValuationInputs(
            pe_ttm=14.0, pe_5y_median=20.0, ev_ebitda=8.0, earnings_history_5y=_history()
        ),
        earnings_history=_history(),
        rs_blend=RSBlendResult(rs_30=0.08, rs_90=0.12, rs_180=0.15, blended=0.12),
    )
    assert result.label == "AVOID"
    assert result.hard_avoid.avoid is True
