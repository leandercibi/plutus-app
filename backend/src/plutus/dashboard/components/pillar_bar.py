from __future__ import annotations

import streamlit as st

from plutus.dashboard.theme import (
    BORDER,
    PILLAR_COLORS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


def pillar_bar(label: str, value: float, max_value: int, color_token: str) -> None:
    pct = 0.0 if max_value == 0 else max(0.0, min(1.0, value / max_value))
    color = PILLAR_COLORS.get(color_token, TEXT_SECONDARY)
    width_pct = int(pct * 100)
    display = (
        f"{value:.2f}" if isinstance(value, float) and value != int(value) else f"{int(value)}"
    )
    st.markdown(
        f"""<div style="display:grid; grid-template-columns: 110px 1fr 50px;
gap: 8px 10px; font-size: 12px; align-items: center; margin: 4px 0;">
  <span style="color: {TEXT_SECONDARY};">{label}</span>
  <div style="background: {BORDER}; border-radius: 3px; height: 6px; overflow: hidden;">
    <div style="width: {width_pct}%; background: {color}; height: 100%;"></div>
  </div>
  <span style="text-align:right; color: {TEXT_PRIMARY};">{display}/{max_value}</span>
</div>""",
        unsafe_allow_html=True,
    )
