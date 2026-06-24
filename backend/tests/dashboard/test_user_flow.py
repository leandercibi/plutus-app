from __future__ import annotations

from tests.dashboard.fixtures import user_flow_view
from tests.dashboard.helpers import run_window


def test_freshness_indicator_red_on_stale() -> None:
    at = run_window("user_flow", user_flow_view(fresh=False))
    assert not at.exception
    # freshness indicator rendered as HTML via st.markdown, not st.error
    md = " ".join(m.value for m in at.markdown)
    assert "Stale" in md


def test_freshness_indicator_green_when_fresh() -> None:
    at = run_window("user_flow", user_flow_view(fresh=True))
    # freshness indicator rendered as HTML via st.markdown, not st.success
    md = " ".join(m.value for m in at.markdown)
    assert "Fresh" in md


def test_run_log_table_renders() -> None:
    at = run_window("user_flow", user_flow_view(fresh=True))
    md = " ".join(m.value for m in at.markdown)
    assert "sunday_full_run" in md
    assert "monday_revalidation" in md
