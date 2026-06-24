from __future__ import annotations

import streamlit as st

from plutus.dashboard.api_client import log_real_fill, manual_exit
from plutus.dashboard.data import PositionView
from plutus.dashboard.theme import (
    BORDER,
    BUY_GREEN,
    LOSS_RED,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)


def _inr(value: object) -> str:
    return f"₹{float(value):,.2f}"


def render(positions: list[PositionView]) -> None:
    st.title("Positions")

    open_positions = [p for p in positions if p.is_open]
    closed_positions = [p for p in positions if not p.is_open]

    st.markdown(f"### Open ({len(open_positions)})")
    if not open_positions:
        st.caption("No open positions.")

    for pos in open_positions:
        st.markdown('<div class="plutus-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(
                f"""<div style="font-size: 14px; font-weight: 500;">{pos.symbol} · {pos.bundle}</div>
<div style="font-size: 11px; color: {TEXT_SECONDARY};">
{pos.age_days}d open · risk {pos.risk_R:.2f}R · realized {pos.realized_R:+.2f}R · MFE {pos.mfe_R:.2f}R</div>""",
                unsafe_allow_html=True,
            )
        with c2:
            color = BUY_GREEN if pos.realized_R >= 0 else LOSS_RED
            st.markdown(
                f'<div style="text-align: right; color: {color}; font-size: 18px; font-weight: 500;">{pos.realized_R:+.2f}R</div>',
                unsafe_allow_html=True,
            )

        # Progress to T1
        progress = max(0.0, min(1.0, pos.elapsed_to_t1_pct / 100.0))
        st.markdown(
            f"""<div style="margin: 10px 0; font-size: 11px; color: {TEXT_TERTIARY};">
Elapsed to T1: {pos.elapsed_to_t1_pct:.0f}%</div>
<div class="plutus-bar-track" style="margin-bottom: 6px;">
  <div class="plutus-bar-fill" style="width:{int(progress*100)}%; background:{BUY_GREEN};"></div>
</div>""",
            unsafe_allow_html=True,
        )

        if pos.trailing_stop is not None:
            st.caption(f"Trailing stop: {_inr(pos.trailing_stop)}")

        # Buttons
        b1, b2 = st.columns(2)
        with b1.popover("📋 Log real fill", use_container_width=True):
            with st.form(key=f"posfill_form_{pos.trade_id}", border=False):
                side = st.selectbox("Side", ["BUY", "SELL"], key=f"posside_{pos.trade_id}")
                qty = st.number_input("Qty", min_value=1, value=1, key=f"posqty_{pos.trade_id}")
                price = st.number_input(
                    "Price", min_value=0.01, value=100.0, step=0.05, key=f"posprice_{pos.trade_id}"
                )
                if st.form_submit_button("Submit fill"):
                    ok, msg = log_real_fill(pos.trade_id, side, int(qty), price)
                    (st.success if ok else st.error)(msg)
        with b2.popover("✖ Manual exit", use_container_width=True):
            with st.form(key=f"posexit_form_{pos.trade_id}", border=False):
                reason = st.text_input("Reason", value="user discretion", key=f"posreason_{pos.trade_id}")
                if st.form_submit_button("Close trade", type="primary"):
                    ok, msg = manual_exit(pos.trade_id, reason)
                    (st.success if ok else st.error)(msg)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(f"### Recently closed (14d) — {len(closed_positions)}")
    for pos in closed_positions:
        delta = (
            f" · slippage Δ {pos.slippage_delta_bps:.1f} bps"
            if pos.slippage_delta_bps is not None
            else ""
        )
        color = BUY_GREEN if pos.realized_R >= 0 else LOSS_RED
        st.markdown(
            f"""<div style="background: {SURFACE}; padding: 8px 12px; border-radius: 6px;
border-left: 2px solid {color}; margin-bottom: 6px; font-size: 12px;">
<b>{pos.symbol}</b> · realized <span style="color:{color}">{pos.realized_R:+.2f}R</span>
· {pos.exit_reason or 'closed'}{delta}</div>""",
            unsafe_allow_html=True,
        )
