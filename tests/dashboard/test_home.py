from __future__ import annotations

from tests.dashboard.fixtures import home_view
from tests.dashboard.helpers import all_markdown, run_window


def test_four_metric_cards_render() -> None:
    at = run_window("home", home_view())
    assert not at.exception
    labels = {m.label for m in at.metric}
    assert labels == {
        "Total capital",
        "Swing allocated",
        "Accumulation allocated",
        "Cash reserve",
    }


def test_metric_values_from_fixture() -> None:
    at = run_window("home", home_view())
    values = {m.label: m.value for m in at.metric}
    assert values["Total capital"] == "₹1,000,000"
    assert values["Cash reserve"] == "₹600,000"


def test_two_panels_render_with_rows() -> None:
    at = run_window("home", home_view())
    md = all_markdown(at)
    assert "Swing mode" in md
    assert "Accumulation mode" in md
    # 3 swing names + 3 accumulation names present
    for sym in ("INFY", "TCS", "WIPRO", "HDFCBANK", "ITC", "RELIANCE"):
        assert sym in md


def test_regime_banner_text_matches_cash_decision_reason() -> None:
    view = home_view(with_cash=True)
    at = run_window("home", view)
    assert view.cash_decision is not None
    # cash_banner renders HTML via st.markdown (not st.info)
    md = all_markdown(at)
    assert view.cash_decision.reason in md


def test_home_has_no_pillar_bars_or_counterfactual_or_benchmarks() -> None:
    at = run_window("home", home_view())
    md = all_markdown(at)
    # pillar bars render "**Technical** x/30" etc; none on Home
    assert "**Technical**" not in md
    assert "**Expectancy**" not in md
    # benchmark strip metric labels must not appear
    metric_labels = {m.label for m in at.metric}
    assert "Plutus" not in metric_labels
    assert "Nifty B&H" not in metric_labels
