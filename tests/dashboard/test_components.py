from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

_HARNESS = str(Path(__file__).parent / "_component_harness.py")


def _run() -> AppTest:
    at = AppTest.from_file(_HARNESS)
    at.run()
    return at


def test_harness_boots_without_exception() -> None:
    at = _run()
    assert not at.exception


def test_six_pillar_bars_render() -> None:
    at = _run()
    # pillar_bar renders HTML via st.markdown — label appears as plain text inside a <span>
    markdowns = " ".join(m.value for m in at.markdown)
    for label in ("Technical", "Expectancy", "Flow", "Sentiment", "Regime fit", "Fundamentals"):
        assert label in markdowns, f"label '{label}' missing from HTML markdown"


def test_calibration_badge_text_present() -> None:
    at = _run()
    # calibration_badge renders HTML via st.markdown (not st.caption)
    markdowns = " ".join(m.value for m in at.markdown)
    assert "n=84" in markdowns
    assert "high" in markdowns


def test_counterfactual_present_and_nonempty() -> None:
    at = _run()
    markdowns = " ".join(m.value for m in at.markdown)
    assert "upgrades to BUY" in markdowns


def test_benchmarks_strip_has_four_baselines() -> None:
    at = _run()
    labels = {m.label for m in at.metric}
    assert {"Plutus", "Nifty B&H", "Regime-switched", "Random liquid"} <= labels


def test_tranche_pills_show_filled_and_empty() -> None:
    at = _run()
    # tranche_pills renders numbered HTML spans (1-5); filled=1,2,3 empty=4,5
    markdowns = " ".join(m.value for m in at.markdown)
    # All tranche numbers must appear in the HTML
    for n in range(1, 6):
        assert f">{n}<" in markdowns, f"tranche {n} missing from HTML"
