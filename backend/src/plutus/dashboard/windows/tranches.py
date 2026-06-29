from __future__ import annotations

import streamlit as st

from plutus.dashboard.api_client import (
    convert_to_swing,
    exit_accum_position,
    log_tranche_fill,
    pause_position,
    resume_position,
)
from plutus.dashboard.components.tranche_pills import tranche_pills
from plutus.dashboard.data import TrancheView
from plutus.dashboard.theme import (
    BUY_GREEN,
    DEAD_ZONE,
    DEAD_ZONE_BG,
    LOSS_RED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


def _inr(value: object) -> str:
    return f"₹{float(value):,.2f}"


def render(tranches: list[TrancheView]) -> None:
    st.title("Tranches")
    if not tranches:
        st.info("No accumulation positions yet.")
        return

    for tr in tranches:
        st.markdown('<div class="plutus-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(
                f'<div style="font-size: 14px; font-weight: 500;">{tr.symbol}</div>',
                unsafe_allow_html=True,
            )
            tranche_pills(tr.seqs_filled, total=tr.total_tranches)
            pl_color = BUY_GREEN if tr.pct_gain_loss >= 0 else LOSS_RED
            st.markdown(
                f"""<div style="font-size: 11px; color: {TEXT_SECONDARY}; margin-top: 6px;">
Avg cost {_inr(tr.avg_cost)} · <span style="color:{pl_color}">{tr.pct_gain_loss:+.1f}%</span>
· thesis {tr.last_thesis_check}: {tr.last_thesis_result}</div>""",
                unsafe_allow_html=True,
            )
        with c2:
            if tr.paused:
                st.markdown(
                    f'<span class="plutus-pill" style="background:{DEAD_ZONE_BG}; color:{DEAD_ZONE};">⏸ Paused</span>',
                    unsafe_allow_html=True,
                )

        if tr.paused and tr.paused_reason:
            st.caption(f"Reason: {tr.paused_reason}")

        b1, b2, b3, b4 = st.columns(4)

        # Add tranche
        next_seq = len(tr.seqs_filled) + 1
        if next_seq <= tr.total_tranches:
            with b1.popover(f"＋ T{next_seq}", use_container_width=True):
                st.caption(f"Log tranche {next_seq} buy for **{tr.symbol}**")
                with st.form(key=f"add_tranche_{tr.position_id}", border=False):
                    tp = st.number_input("Buy price (₹)", min_value=0.01, step=0.05, key=f"atp_{tr.position_id}")
                    tq = st.number_input("Qty", min_value=1, step=1, key=f"atq_{tr.position_id}")
                    if st.form_submit_button(f"Confirm tranche {next_seq}"):
                        ok, msg = log_tranche_fill(tr.position_id, tp, int(tq))
                        (st.success if ok else st.error)(msg)

        # Sell / exit
        with b2.popover("✕ Sell", use_container_width=True):
            st.caption(f"Log full exit for **{tr.symbol}**")
            with st.form(key=f"exit_{tr.position_id}", border=False):
                ep = st.number_input("Sell price (₹)", min_value=0.01, step=0.05, key=f"esp_{tr.position_id}")
                eq = st.number_input("Qty sold", min_value=1, step=1, key=f"esq_{tr.position_id}")
                er = st.text_input("Reason", value="thesis broken", key=f"esr_{tr.position_id}")
                if st.form_submit_button("Confirm sell"):
                    ok, msg = exit_accum_position(tr.position_id, ep, int(eq), er)
                    (st.success if ok else st.error)(msg)

        # Pause / resume
        if tr.paused:
            if b3.button("▶ Resume", key=f"resume_{tr.position_id}", use_container_width=True):
                ok, msg = resume_position(tr.position_id)
                (st.success if ok else st.error)(msg)
        else:
            with b3.popover("⏸ Pause", use_container_width=True):
                with st.form(key=f"pause_form_{tr.position_id}", border=False):
                    reason = st.text_input("Reason for pause", key=f"pausereason_{tr.position_id}")
                    if st.form_submit_button("Confirm pause"):
                        ok, msg = pause_position(tr.position_id, reason or "manual")
                        (st.success if ok else st.error)(msg)

        with b4.popover("↗ Swing", use_container_width=True):
            st.caption("Only available when regime BULL and a swing setup is forming.")
            if st.button("Confirm convert", key=f"confirm_convert_{tr.position_id}"):
                ok, msg = convert_to_swing(tr.position_id)
                (st.success if ok else st.error)(msg)

        st.markdown("</div>", unsafe_allow_html=True)
