from __future__ import annotations

import streamlit as st

from plutus.dashboard.theme import (
    BUY_GREEN,
    LOSS_RED_BG,
    REGIME_BEAR,
    SWING_ACCENT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from plutus.shared.regime.detector import RegimeVerdict
from plutus.shared.risk.cash_position import CashDecision

_LABEL_COLOR = {
    "BULL": BUY_GREEN,
    "BEAR": REGIME_BEAR,
    "SIDEWAYS": SWING_ACCENT,
}


def regime_banner(verdict: RegimeVerdict, cash_decision: CashDecision | None) -> None:
    color = _LABEL_COLOR.get(verdict.label, TEXT_SECONDARY)
    reasons = " · ".join(verdict.reasons[:3]) if verdict.reasons else "no detail"
    body = f"Regime <b>{verdict.label}</b> · {verdict.confidence} confidence. {reasons}."
    if cash_decision is not None and cash_decision.reason:
        body += f" {cash_decision.reason}"
    st.markdown(
        f"""<div class="plutus-banner" style="background: {LOSS_RED_BG};
border-left: 2px solid {color}; color: {TEXT_PRIMARY};">{body}</div>""",
        unsafe_allow_html=True,
    )
