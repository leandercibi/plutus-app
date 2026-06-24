from __future__ import annotations

import pytest

from tests.dashboard.fixtures import strategy_lab_view
from tests.dashboard.helpers import run_window


@pytest.mark.hallmark
def test_strategy_lab_smc_display_only() -> None:
    """C3 hallmark: SMC bundle shows the 'not in live seeding' badge."""
    at = run_window("strategy_lab", strategy_lab_view())
    assert not at.exception
    # SMC note rendered via st.markdown (HTML div), not st.warning
    md = " ".join(m.value for m in at.markdown)
    assert "SMC" in md
    assert "not in live seeding" in md


def test_bundle_and_symbol_selectors_present() -> None:
    at = run_window("strategy_lab", strategy_lab_view())
    # Symbol selectbox label includes count: "Symbol (N in universe)"
    selectbox_labels = {s.label for s in at.selectbox}
    assert "Bundle" in selectbox_labels
    assert any("Symbol" in lbl for lbl in selectbox_labels)


def test_run_button_present() -> None:
    at = run_window("strategy_lab", strategy_lab_view())
    # button label includes ▶ prefix
    button_labels = {b.label for b in at.button}
    assert any("Run backtest" in lbl for lbl in button_labels)
