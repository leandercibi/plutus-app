from __future__ import annotations

from tests.dashboard.fixtures import signal_view
from tests.dashboard.helpers import all_caption, all_markdown, run_window


def test_six_pillar_bars_present() -> None:
    at = run_window("signals", [signal_view()])
    # pillar_bar renders label as plain text in HTML span (not **bold** markdown)
    md = all_markdown(at)
    for label in ("Technical", "Expectancy", "Flow", "Sentiment", "Regime fit", "Fundamentals"):
        assert label in md, f"pillar label '{label}' not found in HTML markdown"


def test_calibration_badge_reflects_band() -> None:
    at = run_window("signals", [signal_view()])
    # calibration_badge renders via st.markdown (not st.caption)
    md = all_markdown(at)
    # fixture has n=84, band=high
    assert "n=84" in md
    assert "high" in md


def test_counterfactual_present_and_nonempty() -> None:
    at = run_window("signals", [signal_view()])
    md = all_markdown(at)
    assert "upgrades to BUY" in md


def test_entry_sl_t1_t2_row_present() -> None:
    at = run_window("signals", [signal_view()])
    # entry/sl/t1/t2 rendered inside HTML <b> tags — values are in the markdown string
    md = all_markdown(at)
    assert "₹1,500.50" in md   # entry
    assert "₹1,440.00" in md   # stop_loss
    assert "₹1,620.00" in md   # target_1


def test_chip_strip_present() -> None:
    at = run_window("signals", [signal_view()])
    # chips rendered via st.markdown (not st.caption); format is :.0f
    md = all_markdown(at)
    assert "delivery 44%" in md     # delivery_pct=44.5 → "44%" with :.0f
    # circuit_hits_90d=0 → chip suppressed (only shown when > 0)
    assert "circuit hits" not in md
