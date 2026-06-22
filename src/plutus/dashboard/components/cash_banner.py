from __future__ import annotations

import streamlit as st

from plutus.dashboard.theme import DEAD_ZONE, DEAD_ZONE_BG
from plutus.shared.risk.cash_position import CashDecision


def cash_banner(decision: CashDecision) -> None:
    """B15 — cash-as-position banner."""
    if not decision.reason:
        return
    st.markdown(
        f"""<div class="plutus-banner" style="background: {DEAD_ZONE_BG};
border-left: 2px solid {DEAD_ZONE}; color: {DEAD_ZONE};">
<b>Cash-as-a-position</b> · {decision.cash_pct_of_pool:.0%} of swing pool held in cash.
{decision.reason}</div>""",
        unsafe_allow_html=True,
    )
