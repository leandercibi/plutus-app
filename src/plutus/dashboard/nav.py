from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import streamlit as st

Domain = Literal["overview", "swing", "accumulation", "configure", "postmortem"]


@dataclass(frozen=True)
class NavItem:
    label: str
    section: Domain


# Sidebar structure (spec 14 §3). Order is binding.
NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("Home", "overview"),
    NavItem("User flow", "overview"),
    NavItem("Signals", "swing"),
    NavItem("Positions", "swing"),
    NavItem("Candidates", "accumulation"),
    NavItem("Tranches", "accumulation"),
    NavItem("Settings", "configure"),
    NavItem("Glossary", "configure"),
    NavItem("Postmortem", "postmortem"),
    NavItem("Calibration", "postmortem"),
    NavItem("Strategy lab", "postmortem"),
)

_SECTION_TITLES: tuple[Domain, ...] = (
    "overview",
    "swing",
    "accumulation",
    "configure",
    "postmortem",
)


def item_labels() -> list[str]:
    return [item.label for item in NAV_ITEMS]


def render_sidebar(active: str | None = None) -> str:
    """Renders the grouped sidebar and returns the selected item label.

    The active item carries a left accent line by domain (swing amber,
    accumulation purple) handled in theme/CSS; here we expose the structure.
    """
    with st.sidebar:
        st.markdown("**Plutus**")
        for section in _SECTION_TITLES:
            st.caption(section)
            for item in NAV_ITEMS:
                if item.section == section:
                    st.markdown(f"- {item.label}")
    return active or NAV_ITEMS[0].label
