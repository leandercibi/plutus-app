from __future__ import annotations

import streamlit as st

from plutus.dashboard.theme import ACCUMULATION_ACCENT, BORDER, TEXT_MUTED


def tranche_pills(seqs_filled: list[int], total: int = 5) -> None:
    html_pieces = []
    for s in range(1, total + 1):
        filled = s in seqs_filled
        bg = ACCUMULATION_ACCENT if filled else BORDER
        fg = "#ffffff" if filled else TEXT_MUTED
        html_pieces.append(
            f'<span class="plutus-tranche" style="background:{bg}; color:{fg};">{s}</span>'
        )
    st.markdown(
        f'<div style="display: flex; align-items: center;">{"".join(html_pieces)}</div>',
        unsafe_allow_html=True,
    )
