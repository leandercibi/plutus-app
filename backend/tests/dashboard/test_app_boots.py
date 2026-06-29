from __future__ import annotations

from streamlit.testing.v1 import AppTest

from plutus.dashboard.nav import item_labels

_APP = "src/plutus/dashboard/app.py"

_EXPECTED_ITEMS = [
    "Home",
    "User flow",
    "Signals",
    "Positions",
    "Candidates",
    "Tranches",
    "Settings",
    "Glossary",
    "Postmortem",
    "Calibration",
    "Strategy lab",
]


def test_app_boots_without_exception() -> None:
    at = AppTest.from_file(_APP)
    at.run()
    assert not at.exception


def test_sidebar_renders_all_expected_items() -> None:
    at = AppTest.from_file(_APP)
    at.run()
    # Sidebar uses st.button per nav item (not st.radio).
    button_labels = {str(b.label) for b in at.sidebar.button}
    for item in _EXPECTED_ITEMS:
        assert item in button_labels, f"Nav button '{item}' not found in sidebar buttons: {button_labels}"


def test_nav_item_labels_match_spec_order() -> None:
    assert item_labels() == _EXPECTED_ITEMS
