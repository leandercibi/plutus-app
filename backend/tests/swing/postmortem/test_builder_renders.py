from __future__ import annotations

import pytest

from plutus.shared.benchmarks.strip import BenchmarkResult
from plutus.swing.postmortem.builder import (
    CalibrationLine,
    PostmortemInputs,
    build_postmortem_md,
)


def _inputs() -> PostmortemInputs:
    return PostmortemInputs(
        week_ending="2025-01-05",
        benchmarks=BenchmarkResult(
            plutus_net_pct=3.2,
            nifty_net_pct=1.1,
            regime_switched_net_pct=0.8,
            random_liquid_net_pct=-0.4,
            plutus_profit_factor=1.8,
            plutus_n_trades=12,
        ),
        calibration_lines=[
            CalibrationLine("trend_70_75", "BULL", 30, 0.6, 0.45, 0.2, 0.7),
        ],
        realized_expectancy_R=0.42,
        forecast_expectancy_R=0.38,
        slippage_divergence_bps=7.5,
        wrong_direction_count=2,
    )


def test_builder_renders_all_sections() -> None:
    md = build_postmortem_md(_inputs())
    assert "Weekly Postmortem" in md
    assert "Net vs benchmarks" in md
    assert "Expectancy" in md
    assert "Bucket calibration" in md


@pytest.mark.hallmark
def test_postmortem_shows_three_benchmarks() -> None:
    """B2: all three baselines present in the strip."""
    md = build_postmortem_md(_inputs())
    assert "Nifty buy & hold" in md
    assert "Regime-switched" in md
    assert "Random liquid baseline" in md


def test_calibration_has_ci_columns() -> None:
    md = build_postmortem_md(_inputs())
    assert "CI" in md
    assert "[0.20, 0.70]" in md


def test_win_rate_is_not_the_headline() -> None:
    """C5: the first metric section is benchmarks/expectancy, not a naked win rate."""
    md = build_postmortem_md(_inputs())
    benchmarks_pos = md.index("Net vs benchmarks")
    # win rate appears only inside the calibration table, which comes later
    win_rate_pos = md.index("win_rate")
    assert benchmarks_pos < win_rate_pos
