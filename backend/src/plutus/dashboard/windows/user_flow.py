from __future__ import annotations

import streamlit as st

from plutus.dashboard.api_client import trigger_monday_reval, trigger_sunday_run
from plutus.dashboard.data import UserFlowView
from plutus.dashboard.theme import (
    BORDER,
    BUY_GREEN,
    LOSS_RED,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)


def render(data: UserFlowView | None) -> None:
    """User flow (spec 14 §12). Weekly cycle + run log + freshness indicator (B11)."""
    st.title("User flow")
    st.caption("Weekly cycle, freshness gate, and manual run triggers.")

    # Freshness indicator
    if data is not None:
        color = BUY_GREEN if data.freshness_ok else LOSS_RED
        label = "Fresh ✓" if data.freshness_ok else "Stale ✗"
        st.markdown(
            f"""<div style="background: {SURFACE}; padding: 10px 14px; border-radius: 6px;
border-left: 2px solid {color}; margin-bottom: 14px; font-size: 12px; color: {TEXT_PRIMARY};">
<b>Data freshness:</b> <span style="color:{color}">{label}</span>
· {data.freshness_detail}
</div>""",
            unsafe_allow_html=True,
        )

    # Manual triggers
    c1, c2 = st.columns(2)
    if c1.button("▶ Run full pipeline (Sunday)", key="run_sunday", use_container_width=True):
        with st.spinner("Triggering…"):
            try:
                run_id = trigger_sunday_run()
                st.success(f"Triggered run {run_id}")
            except Exception as exc:
                st.error(f"Failed: {exc}")
    if c2.button("▶ Monday re-validation", key="run_monday", use_container_width=True):
        with st.spinner("Triggering…"):
            try:
                run_id = trigger_monday_reval()
                st.success(f"Re-validation queued {run_id}")
            except Exception as exc:
                st.error(f"Failed: {exc}")

    # Cycle diagram (textual)
    st.markdown("### Weekly cycle")
    st.markdown(
        f"""<div style="background:{SURFACE}; padding: 14px; border-radius: 8px;
font-size: 12px; color: {TEXT_SECONDARY}; line-height: 2;">
<b style="color:{TEXT_PRIMARY}">Sun 19:00 IST</b> — full pipeline · universe → data → bundles → signals → postmortem<br>
<b style="color:{TEXT_PRIMARY}">Mon 09:10 IST</b> — re-validation against Monday open + weekend news (A15)<br>
<b style="color:{TEXT_PRIMARY}">Mon-Fri 09:30/10:15/11:00/13:30/15:00</b> — exit monitor ticks (B8)<br>
<b style="color:{TEXT_PRIMARY}">Mon-Fri 09:05</b> — freshness assertion · run aborts if stale (B11)<br>
<b style="color:{TEXT_PRIMARY}">Sun 21:00</b> — weekly postmortem publish</div>""",
        unsafe_allow_html=True,
    )

    # Run log
    st.markdown("### Recent runs")
    runs = (data and data.run_log) or []
    if not runs:
        st.caption("No runs logged yet.")
    for row in runs[:10]:
        status = row.status or "running"
        color = BUY_GREEN if status == "OK" else (LOSS_RED if status == "FAILED" else TEXT_TERTIARY)
        st.markdown(
            f"""<div style="display: grid; grid-template-columns: 1fr 100px 140px 80px;
padding: 6px 12px; background: {SURFACE}; border-radius: 4px; margin-bottom: 4px;
font-size: 12px; gap: 10px;">
<span><b>{row.job_name}</b></span>
<span style="color:{TEXT_TERTIARY}">{row.started_at}</span>
<span style="color:{TEXT_TERTIARY}">{row.ended_at or '—'}</span>
<span style="color:{color}; text-align: right;">{status}</span>
</div>""",
            unsafe_allow_html=True,
        )
