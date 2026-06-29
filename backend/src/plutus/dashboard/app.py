from __future__ import annotations

import streamlit as st

from plutus.config.settings import get_settings
from plutus.dashboard import loaders, nav, theme
from plutus.dashboard.windows import (
    calibration,
    candidates,
    glossary,
    home,
    positions,
    postmortem,
    settings,
    signals,
    strategy_lab,
    tranches,
    user_flow,
)
from plutus.db.init_db import init_db
from plutus.db.session import session_scope

st.set_page_config(
    page_title="Plutus",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _load_data() -> None:
    """Load view-models from DB into session_state once per rerun."""
    app_settings = get_settings()
    try:
        with session_scope() as sess:
            st.session_state["home_view"] = loaders.load_home(sess)
            st.session_state["signals_view"] = loaders.load_signals(sess)
            st.session_state["positions_view"] = loaders.load_positions(sess)
            st.session_state["candidates_view"] = loaders.load_candidates(sess)
            st.session_state["tranches_view"] = loaders.load_tranches(sess)
            st.session_state["calibration_view"] = loaders.load_calibration(sess, app_settings)
            st.session_state["postmortem_view"] = loaders.load_postmortem(sess)
            st.session_state["user_flow_view"] = loaders.load_user_flow(sess)
            st.session_state["strategy_lab_view"] = loaders.load_strategy_lab(sess)
    except Exception:  # noqa: BLE001
        st.session_state.setdefault("strategy_lab_view", loaders.load_strategy_lab())
    st.session_state["settings_view"] = loaders.load_settings(app_settings)


_VIEW_KEYS = {
    "Home": "home_view",
    "User flow": "user_flow_view",
    "Signals": "signals_view",
    "Positions": "positions_view",
    "Candidates": "candidates_view",
    "Tranches": "tranches_view",
    "Settings": "settings_view",
    "Postmortem": "postmortem_view",
    "Calibration": "calibration_view",
    "Strategy lab": "strategy_lab_view",
}


def _dispatch(item: str) -> None:
    view_key = _VIEW_KEYS.get(item)
    data = st.session_state.get(view_key) if view_key else None
    list_windows = {
        "Signals": signals.render,
        "Positions": positions.render,
        "Candidates": candidates.render,
        "Tranches": tranches.render,
    }
    object_windows = {
        "Home": home.render,
        "User flow": user_flow.render,
        "Settings": settings.render,
        "Glossary": glossary.render,
        "Postmortem": postmortem.render,
        "Calibration": calibration.render,
        "Strategy lab": strategy_lab.render,
    }
    if item in list_windows:
        list_windows[item](data or [])
    elif item in object_windows:
        object_windows[item](data)


_SECTION_ORDER = ("overview", "swing", "accumulation", "configure", "postmortem")


def _render_sidebar() -> str:
    with st.sidebar:
        st.markdown(
            f"""<div style="padding: 4px 8px 18px;">
<div style="font-weight: 500; color: {theme.TEXT_PRIMARY}; font-size: 15px;">Plutus</div>
<div style="color: {theme.TEXT_TERTIARY}; font-size: 11px;">v2 · trading system</div>
</div>""",
            unsafe_allow_html=True,
        )

        labels_by_section: dict[str, list[str]] = {s: [] for s in _SECTION_ORDER}
        for item in nav.NAV_ITEMS:
            labels_by_section[item.section].append(item.label)

        # default first item
        if "nav_selection" not in st.session_state:
            st.session_state["nav_selection"] = nav.NAV_ITEMS[0].label

        for section in _SECTION_ORDER:
            st.markdown(
                f'<div class="plutus-section-label">{section}</div>',
                unsafe_allow_html=True,
            )
            for label in labels_by_section[section]:
                is_active = st.session_state["nav_selection"] == label
                btn_kwargs = {"key": f"nav_{label}", "use_container_width": True}
                if is_active:
                    btn_kwargs["type"] = "primary"
                if st.button(label, **btn_kwargs):
                    st.session_state["nav_selection"] = label
                    st.rerun()

        st.markdown("---")
        if st.button("↺ Refresh data", key="global_refresh", use_container_width=True):
            st.rerun()

    return st.session_state["nav_selection"]


def _render_top_bar() -> None:
    from plutus.dashboard.components.notification_panel import render_notification_panel

    cols = st.columns([8, 1])
    with cols[1]:
        render_notification_panel()


def main() -> None:
    theme.inject_css()
    init_db()
    _load_data()
    selected = _render_sidebar()
    _render_top_bar()
    _dispatch(selected)


main()
