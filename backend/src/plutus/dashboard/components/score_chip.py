from __future__ import annotations

import streamlit as st

from plutus.dashboard.theme import (
    BUY_GREEN,
    BUY_GREEN_BG,
    DEAD_ZONE,
    DEAD_ZONE_BG,
    LOSS_RED,
    LOSS_RED_BG,
    PANEL,
    TEXT_SECONDARY,
)

_LABEL_STYLE = {
    "BUY": (BUY_GREEN, BUY_GREEN_BG),
    "BUY_WATCH": (DEAD_ZONE, DEAD_ZONE_BG),
    "WATCH": (TEXT_SECONDARY, PANEL),
    "HOLD": (TEXT_SECONDARY, PANEL),
    "AVOID": (LOSS_RED, LOSS_RED_BG),
    "ACCUMULATE_NOW": (BUY_GREEN, BUY_GREEN_BG),
    "BUILD_SLOWLY": (DEAD_ZONE, DEAD_ZONE_BG),
}


def score_chip(label: str, score: int) -> None:
    fg, bg = _LABEL_STYLE.get(label, (TEXT_SECONDARY, PANEL))
    pretty = label.replace("_", "-").lower().capitalize()
    if label in {"BUY", "AVOID", "WATCH", "HOLD"}:
        pretty = label
    elif label == "BUY_WATCH":
        pretty = "Buy-watch"
    st.markdown(
        f"""<span class="plutus-chip" style="background:{bg}; color:{fg};">
{pretty} · {score}</span>""",
        unsafe_allow_html=True,
    )
