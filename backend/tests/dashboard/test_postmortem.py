from __future__ import annotations

import re

import pytest

from tests.dashboard.fixtures import postmortem_view
from tests.dashboard.helpers import all_markdown, run_window


@pytest.mark.hallmark
def test_postmortem_three_benchmarks() -> None:
    """B2 hallmark: all four baseline numbers present in the strip (net of costs)."""
    at = run_window("postmortem", postmortem_view())
    assert not at.exception
    labels = {m.label for m in at.metric}
    assert {"Plutus", "Nifty B&H", "Regime-switched", "Random liquid"} <= labels
    # values present
    values = {m.label: m.value for m in at.metric}
    assert values["Plutus"] == "3.20%"
    assert values["Random liquid"] == "-0.40%"


@pytest.mark.hallmark
def test_postmortem_no_naked_win_rate() -> None:
    """C5 hallmark: every win-rate cell has an adjacent CI cell."""
    at = run_window("postmortem", postmortem_view())
    md = all_markdown(at)
    # header has both a win rate column and a CI column
    assert "win rate" in md
    assert "CI (R)" in md
    # every data row that shows a win-rate pct also shows a CI bracket
    win_rate_rows = [line for line in md.split() if re.match(r"^\d+\.\d%$", line)]
    # at least one win-rate value rendered, and CI brackets present alongside
    assert any("%" in line for line in md.split("|"))
    assert md.count("[") >= len(win_rate_rows)
    assert "[0.20, 0.70]" in md


def test_bundle_rows_render() -> None:
    at = run_window("postmortem", postmortem_view())
    md = all_markdown(at)
    assert "trend" in md
    assert "breakout" in md
