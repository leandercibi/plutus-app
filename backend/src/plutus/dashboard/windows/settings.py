from __future__ import annotations

import streamlit as st

from plutus.dashboard.data import SettingsView


def render(data: SettingsView) -> None:
    """Settings (spec 14 §13). Read-only fields + editable subset; reason required to save."""
    if data is None:
        st.info("No data yet.")
        return
    st.title("Settings")

    for fld in data.fields:
        if fld.editable:
            st.text_input(fld.name, value=fld.value, key=f"edit_{fld.name}")
        else:
            st.markdown(f"{fld.name}: `{fld.value}`")

    st.caption(
        "Editable fields are shown above. Changes must be applied via plutus.env — dashboard save is not yet wired to the config backend."
    )
    reason = st.text_input("Reason for change (for audit log)", value="", key="settings_reason")
    if st.button("Save", key="settings_save", disabled=not reason.strip()):
        st.info(
            "Settings saved to session only — restart the app with an updated plutus.env to persist changes."
        )

    st.divider()
    if st.button("Test Telegram", key="test_telegram"):
        from plutus.dashboard.api_client import test_telegram

        result = test_telegram()
        if result == "ok":
            st.success("Telegram test message sent!")
        else:
            st.error(f"Telegram failed: {result}")
