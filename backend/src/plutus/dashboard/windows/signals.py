from __future__ import annotations

import streamlit as st

from plutus.config.settings import get_settings
from plutus.dashboard.api_client import enter_from_signal, fetch_chart_data, fetch_ltp
from plutus.dashboard.components.calibration_badge import calibration_badge
from plutus.dashboard.components.counterfactual import counterfactual
from plutus.dashboard.components.pillar_bar import pillar_bar
from plutus.dashboard.components.price_chart import render_price_chart
from plutus.dashboard.components.score_chip import score_chip
from plutus.dashboard.data import SignalView
from plutus.dashboard.theme import (
    BORDER,
    LOSS_RED,
    LOSS_RED_BG,
    PANEL,
    SURFACE,
    SWING_ACCENT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)
from plutus.shared.calibration.deadzone import deadzone_label

_PILLAR_SPECS = (
    ("Technical", "technical", 30),
    ("Expectancy", "expectancy", 25),
    ("Flow", "flow", 15),
    ("Sentiment", "sentiment", 5),
    ("Regime fit", "regime_fit", 15),
    ("Fundamentals", "fundamentals", 10),
)


def _inr(value: object) -> str:
    return f"₹{float(value):,.2f}"


def _chip(text: str, fg: str, bg: str) -> str:
    return f'<span class="plutus-pill" style="background:{bg}; color:{fg}; margin-right: 6px;">{text}</span>'


def _summary_row(sig: SignalView) -> None:
    """Compact one-line summary shown when the signal is collapsed."""
    rr = (float(sig.target_1) - float(sig.entry)) / max(
        float(sig.entry) - float(sig.stop_loss), 1e-9
    )
    st.markdown(
        f"""<div style="display:grid; grid-template-columns: 100px 70px 80px 1fr 80px;
gap: 12px; align-items: center; font-size: 12px; padding: 4px 0;">
  <span style="font-weight:500; color:{TEXT_PRIMARY};">{sig.symbol}</span>
  <span style="color:{TEXT_TERTIARY};">{sig.bundle}</span>
  <span style="color:{TEXT_SECONDARY};">{_inr(sig.entry)}</span>
  <span style="color:{TEXT_TERTIARY};">R:R {rr:.2f}× · n={sig.calibration_n}</span>
  <span style="text-align:right;">{sig.label} · {sig.score}</span>
</div>""",
        unsafe_allow_html=True,
    )


def _detail_body(sig: SignalView, settings) -> None:
    """Full detail panel shown when the signal is expanded."""
    chip_label = deadzone_label(sig.score, settings)

    # Header row: chips on the right, levels on the left.
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(
            f"""<div style="font-size: 13px; color: {TEXT_SECONDARY};">
Entry <b style="color:{TEXT_PRIMARY}">{_inr(sig.entry)}</b> ·
SL <b style="color:{TEXT_PRIMARY}">{_inr(sig.stop_loss)}</b> ·
T1 <b style="color:{TEXT_PRIMARY}">{_inr(sig.target_1)}</b> ·
T2 <b style="color:{TEXT_PRIMARY}">{_inr(sig.target_2)}</b></div>""",
            unsafe_allow_html=True,
        )
    with c2:
        score_chip(chip_label, sig.score)
        calibration_badge(sig.calibration_n, sig.calibration_band)

    # Pillar bars
    for label, key, mx in _PILLAR_SPECS:
        pillar_bar(label, getattr(sig.pillars, key), mx, key)

    # Chips — only render fields the pipeline actually populated.
    chips: list[str] = []
    if sig.delivery_pct > 0:
        chips.append(_chip(f"delivery {sig.delivery_pct:.0f}%", TEXT_PRIMARY, PANEL))
    if sig.adv_use_pct > 0:
        chips.append(_chip(f"ADV use {sig.adv_use_pct:.1f}%", TEXT_SECONDARY, PANEL))
    if sig.circuit_hits_90d > 0:
        chips.append(
            _chip(f"⚠ circuit hits {sig.circuit_hits_90d} (90d)", LOSS_RED, LOSS_RED_BG)
        )
    if sig.earnings_in_window:
        chips.append(_chip("⚠ earnings in window", LOSS_RED, LOSS_RED_BG))
    if sig.sector_heat > 0:
        chips.append(_chip(f"sector heat {sig.sector_heat:.1f}R", TEXT_SECONDARY, PANEL))
    if chips:
        st.markdown(
            f'<div style="margin: 10px 0;">{"".join(chips)}</div>',
            unsafe_allow_html=True,
        )

    # Counterfactual
    if sig.counterfactual:
        counterfactual(sig.counterfactual)

    # Price chart (lazy-loaded on click)
    chart_key = f"chart_sig_{sig.id}"
    if st.button(f"📈 Price chart · {sig.bundle}", key=f"btn_{chart_key}"):
        st.session_state[chart_key] = True
        st.session_state.pop(f"chartdata_{chart_key}", None)
    if st.session_state.get(chart_key):
        if f"chartdata_{chart_key}" not in st.session_state:
            with st.spinner(f"Loading {sig.symbol} chart…"):
                chart_data = fetch_chart_data(sig.symbol, signal_id=sig.id)
            if chart_data:
                st.session_state[f"chartdata_{chart_key}"] = chart_data
            else:
                st.warning("Could not load chart — is the API running?")
        chart_data = st.session_state.get(f"chartdata_{chart_key}")
        if chart_data:
            render_price_chart(chart_data, chart_key=chart_key)

    # Action — log a real broker entry fill (creates the trade record too)
    with st.popover("📋 Log entry fill", use_container_width=False):
        st.caption("Opens a trade and logs your broker fill in one step.")
        ltp_key = f"ltp_sig_{sig.id}"
        if ltp_key not in st.session_state:
            ltp = fetch_ltp(sig.symbol)
            st.session_state[ltp_key] = ltp if ltp else float(sig.entry)
        side = st.selectbox("Side", ["BUY", "SELL"], key=f"side_{sig.id}")
        qty = st.number_input("Qty", min_value=1, value=1, key=f"qty_{sig.id}")
        price = st.number_input(
            "Price",
            min_value=0.01,
            value=st.session_state[ltp_key],
            step=0.05,
            key=f"price_{sig.id}",
        )
        total = price * int(qty)
        st.markdown(f"**Total: ₹{total:,.2f}**")
        if st.button("Submit fill", key=f"fill_btn_{sig.id}"):
            ok, msg = enter_from_signal(sig.id, side, int(qty), price)
            (st.success if ok else st.error)(msg)
            if ok:
                del st.session_state[ltp_key]


def render(signals: list[SignalView]) -> None:
    settings = get_settings()

    st.title("Signals")
    if not signals:
        st.info("No signals yet — trigger a run from User flow.")
        return

    # Filters
    f1, f2, f3, f4 = st.columns(4)
    regimes = sorted({s.regime for s in signals})
    bundles = sorted({s.bundle for s in signals})
    labels = sorted({s.label for s in signals})
    bands = sorted({s.calibration_band for s in signals})
    sel_regime = f1.selectbox("Regime", ["All", *regimes], key="f_regime")
    sel_bundle = f2.selectbox("Bundle", ["All", *bundles], key="f_bundle")
    sel_label = f3.selectbox("Label", ["All", *labels], key="f_label")
    sel_band = f4.selectbox("Calibration", ["All", *bands], key="f_band")

    # Sort controls.
    s1, s2 = st.columns([2, 1])
    sort_key = s1.selectbox(
        "Sort by",
        options=[
            "Label & score (BUY first)",
            "R:R drawn (high → low)",
            "Calibration n (high → low)",
            "Score (high → low)",
            "Symbol (A → Z)",
        ],
        index=0,
        key="f_sort",
    )
    sort_dir_desc = s2.toggle("Descending", value=True, key="f_sort_dir")

    def passes(s: SignalView) -> bool:
        return (
            (sel_regime == "All" or s.regime == sel_regime)
            and (sel_bundle == "All" or s.bundle == sel_bundle)
            and (sel_label == "All" or s.label == sel_label)
            and (sel_band == "All" or s.calibration_band == sel_band)
        )

    filtered = [s for s in signals if passes(s)]

    # Sort. Label rank puts BUY at the top; score is the secondary key.
    _LABEL_RANK = {"BUY": 0, "BUY_WATCH": 1, "WATCH": 2, "HOLD": 3, "AVOID": 4}

    def _drawn_rr(s: SignalView) -> float:
        risk = float(s.entry) - float(s.stop_loss)
        if risk <= 0:
            return 0.0
        return (float(s.target_1) - float(s.entry)) / risk

    if sort_key.startswith("Label & score"):
        filtered.sort(key=lambda s: (_LABEL_RANK.get(s.label, 9), -s.score))
        if not sort_dir_desc:
            filtered.reverse()
    elif sort_key.startswith("R:R"):
        filtered.sort(key=_drawn_rr, reverse=sort_dir_desc)
    elif sort_key.startswith("Calibration"):
        filtered.sort(key=lambda s: s.calibration_n, reverse=sort_dir_desc)
    elif sort_key.startswith("Score"):
        filtered.sort(key=lambda s: s.score, reverse=sort_dir_desc)
    else:  # Symbol
        filtered.sort(key=lambda s: s.symbol, reverse=not sort_dir_desc)

    st.caption(
        f"{len(filtered)} of {len(signals)} unique (symbol · bundle) signals "
        f"· deduped to the most recent per pair · sorted by {sort_key}"
    )

    # Header bar
    st.markdown(
        f"""<div style="display:grid; grid-template-columns: 100px 70px 80px 1fr 80px;
gap: 12px; padding: 6px 12px; font-size: 10px; color: {TEXT_TERTIARY};
text-transform: lowercase; letter-spacing: 0.5px; border-bottom: 0.5px solid {BORDER};">
<span>symbol</span><span>bundle</span><span>entry</span><span>R:R · calibration</span>
<span style="text-align:right;">label · score</span>
</div>""",
        unsafe_allow_html=True,
    )

    # Expandable signal rows. The first 3 in the chosen sort order start
    # expanded so the user immediately sees the rows they were sorting toward.
    top3_ids = {s.id for s in filtered[:3]}
    for sig in filtered:
        label = f"{sig.symbol} · {sig.bundle} · {sig.label} {sig.score}"
        with st.expander(label, expanded=(sig.id in top3_ids)):
            _detail_body(sig, settings)
