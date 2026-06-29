from __future__ import annotations

import streamlit as st

from plutus.dashboard.api_client import (
    exit_accum_position,
    fetch_chart_data,
    fetch_ltp,
    log_tranche_fill,
    start_accum_position,
)
from plutus.dashboard.components.pillar_bar import pillar_bar
from plutus.dashboard.components.price_chart import render_price_chart
from plutus.dashboard.data import CandidateView
from plutus.dashboard.theme import BUY_GREEN, LOSS_RED, TEXT_SECONDARY


def _label_color(label: str) -> str:
    return {
        "ACCUMULATE_NOW": BUY_GREEN,
        "BUILD_SLOWLY": "#f0a500",
        "WATCH": TEXT_SECONDARY,
        "AVOID": LOSS_RED,
    }.get(label, TEXT_SECONDARY)


def render(candidates: list[CandidateView]) -> None:
    """Accumulation candidates (spec 14 §7)."""
    st.title("Candidates")

    for cand in candidates:
        st.markdown('<div class="plutus-card">', unsafe_allow_html=True)

        col_info, col_btn = st.columns([3, 1])
        with col_info:
            label_color = _label_color(cand.label)
            st.markdown(
                f'<span style="font-weight:600">{cand.symbol}</span>'
                f' &nbsp;<span style="color:{label_color};font-size:12px">{cand.label}</span>',
                unsafe_allow_html=True,
            )

        with col_btn:
            _render_action_button(cand)

        pillar_bar("Quality", cand.quality, 30, "fundamentals")
        pillar_bar("Growth", cand.growth, 25, "expectancy")
        pillar_bar("Valuation", cand.valuation, 30, "flow")
        pillar_bar("RS blend", cand.rs_blend, 15, "technical")

        cap = " · valuation capped" if cand.valuation_capped else ""
        st.caption(
            f"RS 30/90/180: {cand.rs_30*100:+.1f}%/{cand.rs_90*100:+.1f}%/{cand.rs_180*100:+.1f}% vs Nifty · "
            f"CAGR EPS 3y {cand.cagr_eps_3y:.1f}% / 5y {cand.cagr_eps_5y:.1f}%{cap}"
        )

        for reason in cand.hard_avoid_reasons:
            st.error(f"hard avoid: {reason}")

        chart_key = f"chart_cand_{cand.symbol}"
        if st.button(f"📈 Price chart", key=f"btn_{chart_key}"):
            st.session_state[chart_key] = True
            st.session_state.pop(f"chartdata_{chart_key}", None)
        if st.session_state.get(chart_key):
            if f"chartdata_{chart_key}" not in st.session_state:
                with st.spinner(f"Loading {cand.symbol} chart…"):
                    chart_data = fetch_chart_data(cand.symbol)
                if chart_data:
                    st.session_state[f"chartdata_{chart_key}"] = chart_data
                else:
                    st.warning("Could not load chart — is the API running?")
            chart_data = st.session_state.get(f"chartdata_{chart_key}")
            if chart_data:
                render_price_chart(chart_data, chart_key=chart_key)

        st.markdown("</div>", unsafe_allow_html=True)


def _ltp_key(sym: str, tag: str) -> str:
    return f"ltp_{sym}_{tag}"


def _fetch_and_store_ltp(sym: str, tag: str) -> None:
    key = _ltp_key(sym, tag)
    if key not in st.session_state:
        price = fetch_ltp(sym)
        st.session_state[key] = price or 0.0


def _render_action_button(cand: CandidateView) -> None:
    """Show Start / Add tranche / Exit button depending on position state."""
    sym = cand.symbol

    if cand.position_id is None:
        with st.popover("＋ Start", use_container_width=True):
            st.caption(f"Open tranche 1 of 5 for **{sym}**")
            _fetch_and_store_ltp(sym, "start")
            price = st.number_input(
                "Buy price (₹)", min_value=0.01, step=0.05,
                value=st.session_state[_ltp_key(sym, "start")],
                key=f"sp_{sym}",
            )
            qty = st.number_input("Qty (shares)", min_value=1, step=1, key=f"sq_{sym}")
            total = price * int(qty)
            st.markdown(f"**Total: ₹{total:,.2f}**")
            if st.button("Confirm buy — tranche 1", key=f"sbtn_{sym}"):
                ok, msg = start_accum_position(sym, price, int(qty))
                (st.success if ok else st.error)(msg)
                if ok:
                    del st.session_state[_ltp_key(sym, "start")]

    elif cand.tranches_filled < cand.total_tranches:
        next_seq = cand.tranches_filled + 1
        with st.popover(f"＋ Tranche {next_seq}", use_container_width=True):
            st.caption(f"Log tranche {next_seq} of {cand.total_tranches} for **{sym}**")
            _fetch_and_store_ltp(sym, "tranche")
            price = st.number_input(
                "Buy price (₹)", min_value=0.01, step=0.05,
                value=st.session_state[_ltp_key(sym, "tranche")],
                key=f"tp_{sym}",
            )
            qty = st.number_input("Qty (shares)", min_value=1, step=1, key=f"tq_{sym}")
            total = price * int(qty)
            st.markdown(f"**Total: ₹{total:,.2f}**")
            if st.button(f"Confirm buy — tranche {next_seq}", key=f"tbtn_{sym}"):
                ok, msg = log_tranche_fill(cand.position_id, price, int(qty))
                (st.success if ok else st.error)(msg)
                if ok:
                    del st.session_state[_ltp_key(sym, "tranche")]

        with st.popover("✕ Exit", use_container_width=True):
            st.caption(f"Log full exit for **{sym}** ({cand.tranches_filled}/{cand.total_tranches} tranches)")
            _fetch_and_store_ltp(sym, "exit")
            price = st.number_input(
                "Sell price (₹)", min_value=0.01, step=0.05,
                value=st.session_state[_ltp_key(sym, "exit")],
                key=f"ep_{sym}",
            )
            qty = st.number_input("Qty sold", min_value=1, step=1, key=f"eq_{sym}")
            total = price * int(qty)
            st.markdown(f"**Total proceeds: ₹{total:,.2f}**")
            reason = st.text_input("Reason", value="thesis broken", key=f"er_{sym}")
            if st.button("Confirm sell", key=f"ebtn_{sym}"):
                ok, msg = exit_accum_position(cand.position_id, price, int(qty), reason)
                (st.success if ok else st.error)(msg)
                if ok:
                    del st.session_state[_ltp_key(sym, "exit")]

    else:
        st.markdown(
            f'<span style="font-size:11px;color:{BUY_GREEN}">✓ Full (5/5)</span>',
            unsafe_allow_html=True,
        )
