from __future__ import annotations

from tests.dashboard.fixtures import settings_view
from tests.dashboard.helpers import run_window


def test_save_disabled_when_reason_empty() -> None:
    at = run_window("settings", settings_view())
    assert not at.exception
    save = next(b for b in at.button if b.label == "Save")
    assert save.disabled


def test_save_enabled_after_reason_entered() -> None:
    at = run_window("settings", settings_view())
    reason = next(t for t in at.text_input if "Reason for change" in t.label)
    reason.set_value("lowering risk after drawdown").run()
    save = next(b for b in at.button if b.label == "Save")
    assert not save.disabled


def test_editable_and_readonly_fields_render() -> None:
    at = run_window("settings", settings_view())
    editable_labels = {t.label for t in at.text_input}
    assert "risk_per_trade_pct" in editable_labels
    md = " ".join(m.value for m in at.markdown)
    assert "db_url" in md  # read-only field
