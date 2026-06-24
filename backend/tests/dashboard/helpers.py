from __future__ import annotations

from pathlib import Path
from typing import Any

from streamlit.testing.v1 import AppTest

_WINDOW_HARNESS = str(Path(__file__).parent / "_window_harness.py")
_APP = "src/plutus/dashboard/app.py"


def run_window(window: str, data: Any) -> AppTest:
    at = AppTest.from_file(_WINDOW_HARNESS)
    at.session_state["window"] = window
    at.session_state["data"] = data
    at.run()
    return at


def run_app(active_item: str, view_key: str, data: Any) -> AppTest:
    at = AppTest.from_file(_APP)
    at.session_state["active_item"] = active_item
    at.session_state[view_key] = data
    at.run()
    return at


def all_markdown(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def all_caption(at: AppTest) -> str:
    return " ".join(c.value for c in at.caption)
