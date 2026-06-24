from __future__ import annotations

import pytest

from tests.dashboard.fixtures import signal_view
from tests.dashboard.helpers import all_markdown, run_window


@pytest.mark.hallmark
def test_signals_dead_zone_shows_buy_watch() -> None:
    """B17 hallmark: a signal scoring 70 (inside the 67..73 soft dead zone) renders
    as a BUY_WATCH chip, not BUY or WATCH."""
    at = run_window("signals", [signal_view(score=70)])
    assert not at.exception
    md = all_markdown(at)
    # score_chip humanizes BUY_WATCH → "Buy-watch · 70"
    assert "Buy-watch · 70" in md
    # plain BUY or WATCH chip must not appear at score=70
    assert "BUY · 70" not in md
    assert "WATCH · 70" not in md


def test_score_above_dead_zone_is_buy() -> None:
    at = run_window("signals", [signal_view(score=80)])
    md = all_markdown(at)
    assert "BUY · 80" in md


def test_score_below_dead_zone_is_watch() -> None:
    at = run_window("signals", [signal_view(score=60)])
    md = all_markdown(at)
    assert "WATCH · 60" in md
