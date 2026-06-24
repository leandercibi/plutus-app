from __future__ import annotations

from typing import Any

import streamlit as st

from plutus.dashboard.api_client import dismiss_notification, fetch_notifications
from plutus.dashboard.theme import (
    BORDER,
    BUY_GREEN,
    LOSS_RED,
    PANEL,
    SURFACE,
    SWING_ACCENT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)

_SEVERITY_COLORS: dict[str, tuple[str, str]] = {
    "URGENT": (LOSS_RED, "#2a1f1f"),
    "WARNING": (SWING_ACCENT, "#2a2510"),
    "INFO": ("#8aa9e0", "#1f2b3a"),
}

_KIND_ICONS: dict[str, str] = {
    "SL_PROXIMITY": "⚠",
    "SL_BREACH": "🛑",
    "SL_WARNING": "⚠",
    "T1_PROXIMITY": "🎯",
    "T1_HIT": "🎯",
    "T2_HIT": "🎯",
    "PNL_UPDATE": "📊",
    "PRICE_ALERT": "📈",
    "ENTRY": "🟢",
    "MONDAY_REVALIDATION": "📋",
    "REGIME_FLIP": "🔄",
}


def render_notification_panel() -> None:
    notifications = fetch_notifications()
    count = len(notifications)

    bell_color = LOSS_RED if any(n["severity"] == "URGENT" for n in notifications) else (
        SWING_ACCENT if count > 0 else TEXT_MUTED
    )

    with st.popover(f"🔔 {count}" if count > 0 else "🔔", use_container_width=False):
        if not notifications:
            st.markdown(
                f'<div style="padding:12px;color:{TEXT_TERTIARY};font-size:12px;">'
                f"No new notifications</div>",
                unsafe_allow_html=True,
            )
            return

        st.markdown(
            f'<div style="font-size:13px;font-weight:500;color:{TEXT_PRIMARY};'
            f'padding:4px 0 8px;border-bottom:0.5px solid {BORDER};">'
            f"Notifications ({count})</div>",
            unsafe_allow_html=True,
        )

        for n in notifications:
            _render_notification(n)


def _render_notification(n: dict[str, Any]) -> None:
    fg, bg = _SEVERITY_COLORS.get(n["severity"], (TEXT_SECONDARY, PANEL))
    icon = _KIND_ICONS.get(n["kind"], "📋")
    created = n["created_at"][:16].replace("T", " ")

    st.markdown(
        f'<div style="background:{bg};border-radius:6px;padding:8px 10px;'
        f'margin:6px 0;border-left:3px solid {fg};">'
        f'<div style="font-size:12px;font-weight:500;color:{fg};">'
        f'{icon} {n["title"]}</div>'
        f'<div style="font-size:11px;color:{TEXT_SECONDARY};margin-top:2px;">'
        f'{n["body"]}</div>'
        f'<div style="font-size:10px;color:{TEXT_TERTIARY};margin-top:4px;">'
        f"{created}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if st.button("Dismiss", key=f"dismiss_{n['id']}", type="secondary"):
        dismiss_notification(n["id"])
        st.rerun()
