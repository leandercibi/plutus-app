from __future__ import annotations

from typing import Literal

import streamlit as st

from plutus.dashboard.theme import (
    BUY_GREEN,
    BUY_GREEN_BG,
    DEAD_ZONE,
    DEAD_ZONE_BG,
    LOSS_RED,
    LOSS_RED_BG,
)

_BAND_STYLE = {
    "high": (BUY_GREEN, BUY_GREEN_BG),
    "medium": (DEAD_ZONE, DEAD_ZONE_BG),
    "low": (LOSS_RED, LOSS_RED_BG),
}


def calibration_badge(n: int, band: Literal["low", "medium", "high"]) -> None:
    fg, bg = _BAND_STYLE.get(band, _BAND_STYLE["low"])
    st.markdown(
        f"""<span class="plutus-pill" style="background: {bg}; color: {fg};">
calibration n={n} · {band}</span>""",
        unsafe_allow_html=True,
    )
