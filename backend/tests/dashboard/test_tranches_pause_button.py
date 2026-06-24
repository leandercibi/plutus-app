from __future__ import annotations

from tests.dashboard.fixtures import tranche_views
from tests.dashboard.helpers import run_window


def test_tranche_pills_render() -> None:
    at = run_window("tranches", tranche_views())
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    # tranche_pills renders <span ...>N</span> — check HTML number pattern
    for n in range(1, 6):
        assert f">{n}<" in md, f"tranche pill {n} missing from HTML"


def test_pause_button_present_for_active_position() -> None:
    at = run_window("tranches", tranche_views())
    labels = [b.label for b in at.button]
    # Streamlit renders inner form submit buttons, not popover trigger labels.
    # HDFCBANK (active): inside popover "⏸ Pause" → form submit "Confirm pause"
    # ITC (paused): button "▶ Resume"
    assert "Confirm pause" in labels
    assert "▶ Resume" in labels
    assert "Confirm convert" in labels


def test_paused_position_shows_reason() -> None:
    at = run_window("tranches", tranche_views())
    # paused_reason rendered via st.caption, not st.warning
    captions = " ".join(c.value for c in at.caption)
    assert "quality pillar dropped" in captions


def test_pause_button_click_runs_without_error() -> None:
    at = run_window("tranches", tranche_views())
    # form submit inside the pause popover
    pause = next(b for b in at.button if b.label == "Confirm pause")
    pause.click().run()
    assert not at.exception
