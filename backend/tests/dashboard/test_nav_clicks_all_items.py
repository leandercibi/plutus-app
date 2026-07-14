"""End-to-end nav test: simulates clicking every sidebar item.

Catches regressions like passing an empty string into st.session_state.get(),
which Streamlit rejects with 'The `key` argument must be non-empty'.
The window-level tests don't exercise the full app dispatch path, so this
test is the safety net for app.py-level bugs.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from plutus.dashboard.nav import item_labels

_APP = "src/plutus/dashboard/app.py"


@pytest.mark.parametrize("nav_label", item_labels())
def test_clicking_nav_item_does_not_crash(nav_label: str) -> None:
    at = AppTest.from_file(_APP, default_timeout=20)
    at.run()
    assert not at.exception, f"App failed to boot before navigation: {at.exception}"

    # Click the sidebar button for this nav item, then re-run
    btn = next(b for b in at.sidebar.button if str(b.label) == nav_label)
    btn.click().run()

    assert not at.exception, (
        f"Clicking '{nav_label}' raised: {[str(e.value) for e in at.exception]}"
    )
