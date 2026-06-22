from __future__ import annotations

from tests.dashboard.fixtures import strategy_lab_view
from tests.dashboard.helpers import run_window


def test_walkforward_button_renders() -> None:
    at = run_window("strategy_lab", strategy_lab_view())
    assert not at.exception
    button_labels = {b.label for b in at.button}
    assert any("Walk-Forward" in lbl for lbl in button_labels)


def test_walkforward_selectors_present() -> None:
    at = run_window("strategy_lab", strategy_lab_view())
    selectbox_labels = {s.label for s in at.selectbox}
    assert any("WF Bundle" in lbl for lbl in selectbox_labels)
    assert any("WF Symbol" in lbl for lbl in selectbox_labels)


def test_walkforward_number_inputs_present() -> None:
    at = run_window("strategy_lab", strategy_lab_view())
    number_labels = {n.label for n in at.number_input}
    assert any("Window" in lbl for lbl in number_labels)
    assert any("Step" in lbl for lbl in number_labels)
