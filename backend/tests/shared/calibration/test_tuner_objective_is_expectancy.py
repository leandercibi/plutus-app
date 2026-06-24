from __future__ import annotations

from datetime import datetime

import pytest

from plutus.config.settings import Settings
from plutus.shared.calibration.regime_partition import TradeOutcome
from plutus.shared.calibration.tuner import CandidateVariant, Tuner


def _outcomes(rs: list[float]) -> list[TradeOutcome]:
    return [
        TradeOutcome(
            trade_id=i,
            bundle="trend",
            regime_at_signal="BULL",
            score_bucket="score_70_75",
            realized_R=r,
            horizon_days=5,
            closed_at=datetime(2025, 1, 1),
            is_paper=False,
        )
        for i, r in enumerate(rs)
    ]


@pytest.mark.hallmark
def test_tuner_objective_is_expectancy_not_win_rate() -> None:
    """A14/C5: a high-win-rate variant with LOW expectancy must not be proposed
    over a lower-win-rate variant with HIGH expectancy."""
    # Variant HIGH_WR: 90% wins of +0.1R, 10% losses of -2.0R -> win rate 0.9, E = -0.11R
    high_wr = [0.1] * 54 + [-2.0] * 6
    # Variant HIGH_E: 50% wins of +1.5R, 50% losses of -0.4R -> win rate 0.5, E = +0.55R
    high_e = [1.5, -0.4] * 60

    variants = [
        CandidateVariant(
            bundle="trend",
            regime="BULL",
            parameter="stop_atr_mult",
            old_value=1.0,
            proposed_value=1.5,
            outcomes=_outcomes(high_wr),
            p_value=0.001,
        ),
        CandidateVariant(
            bundle="trend",
            regime="BULL",
            parameter="target_atr_mult",
            old_value=2.0,
            proposed_value=2.5,
            outcomes=_outcomes(high_e),
            p_value=0.001,
        ),
    ]
    tuner = Tuner(Settings(_env_file=None))
    proposals = tuner.propose(variants)

    proposed_params = {p.parameter for p in proposals}
    # the high-win-rate negative-expectancy variant must NOT be proposed
    assert "stop_atr_mult" not in proposed_params
    # the high-expectancy variant should be proposed
    assert "target_atr_mult" in proposed_params


def test_auto_apply_off_by_default() -> None:
    high_e = [1.5, -0.4] * 60
    variants = [
        CandidateVariant(
            bundle="trend",
            regime="BULL",
            parameter="target_atr_mult",
            old_value=2.0,
            proposed_value=2.5,
            outcomes=_outcomes(high_e),
            p_value=0.001,
        )
    ]
    tuner = Tuner(Settings(_env_file=None))  # auto_tune_enabled defaults False
    proposals = tuner.propose(variants)
    assert all(p.auto_apply_eligible is False for p in proposals)


def test_family_correction_required() -> None:
    """A single uncorrected significant bucket with a weak family p-value -> no proposal."""
    high_e = [1.5, -0.4] * 60
    variants = [
        CandidateVariant(
            bundle="trend",
            regime="BULL",
            parameter="target_atr_mult",
            old_value=2.0,
            proposed_value=2.5,
            outcomes=_outcomes(high_e),
            p_value=0.6,  # fails BH at q=0.10
        )
    ]
    tuner = Tuner(Settings(_env_file=None))
    assert tuner.propose(variants) == []
