from __future__ import annotations

import streamlit as st


def counterfactual(text: str) -> None:
    if not text:
        return
    st.markdown(
        f"""<div class="plutus-counterfactual">
<span style="margin-right: 4px;">💡</span>{text}</div>""",
        unsafe_allow_html=True,
    )
