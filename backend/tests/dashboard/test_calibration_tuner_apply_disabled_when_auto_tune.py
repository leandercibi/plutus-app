from __future__ import annotations

from tests.dashboard.fixtures import calibration_view
from tests.dashboard.helpers import run_window


def test_apply_disabled_when_auto_tune_enabled() -> None:
    at = run_window("calibration", calibration_view(auto_tune=True))
    assert not at.exception
    apply_buttons = [b for b in at.button if b.label == "Apply"]
    assert apply_buttons
    assert all(b.disabled for b in apply_buttons)


def test_apply_always_disabled_until_wired() -> None:
    # Manual apply is not yet wired to a backend endpoint.
    # The button must be disabled in all cases so users don't expect a write.
    at = run_window("calibration", calibration_view(auto_tune=False))
    apply_buttons = [b for b in at.button if b.label == "Apply"]
    assert apply_buttons
    assert all(b.disabled for b in apply_buttons)


def test_calibration_lines_show_ci_and_sprt() -> None:
    at = run_window("calibration", calibration_view(auto_tune=False))
    # HTML table uses {:+.2f} format → "+0.20" not "0.20"
    md = " ".join(m.value for m in at.markdown)
    assert "+0.20" in md  # ci_low_R formatted with sign
    assert "+0.70" in md  # ci_high_R formatted with sign
    assert "continue" in md  # sprt_state
