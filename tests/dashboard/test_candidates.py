from __future__ import annotations

from tests.dashboard.fixtures import candidate_views
from tests.dashboard.helpers import run_window


def test_candidates_render_with_labels() -> None:
    at = run_window("candidates", candidate_views())
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    # symbol and label now rendered in separate HTML spans within the same st.markdown call
    assert "HDFCBANK" in md
    assert "ACCUMULATE_NOW" in md
    assert "YESBANK" in md
    assert "AVOID" in md


def test_hard_avoid_badges_visible_when_set() -> None:
    at = run_window("candidates", candidate_views())
    errors = " ".join(e.value for e in at.error)
    assert "D/E breach" in errors
    assert "EPS collapse" in errors


def test_pillar_bars_and_rs_present() -> None:
    at = run_window("candidates", candidate_views())
    # pillar_bar renders label as plain text inside HTML spans (not bold markdown)
    md = " ".join(m.value for m in at.markdown)
    captions = " ".join(c.value for c in at.caption)
    assert "Quality" in md
    assert "Valuation" in md
    assert "RS 30/90/180" in captions
