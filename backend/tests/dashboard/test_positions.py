from __future__ import annotations

from tests.dashboard.fixtures import position_views
from tests.dashboard.helpers import run_window


def test_positions_render_open_and_closed() -> None:
    at = run_window("positions", position_views())
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "INFY" in md  # open
    assert "TCS" in md  # closed


def test_open_position_buttons_present() -> None:
    at = run_window("positions", position_views())
    # Popovers are rendered as buttons; form submit buttons are the action triggers.
    labels = {b.label for b in at.button}
    # popover trigger buttons
    assert "📋 Log real fill" in labels or "Submit fill" in labels
    assert "✖ Manual exit" in labels or "Close trade" in labels


def test_closed_position_shows_slippage_delta() -> None:
    at = run_window("positions", position_views())
    md = " ".join(m.value for m in at.markdown)
    assert "slippage Δ 6.2 bps" in md
