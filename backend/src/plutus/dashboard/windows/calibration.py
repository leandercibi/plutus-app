from __future__ import annotations

import streamlit as st

from plutus.dashboard.data import CalibrationView
from plutus.dashboard.theme import (
    BORDER,
    BUY_GREEN,
    DEAD_ZONE,
    LOSS_RED,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)

_BAND_COLOR = {"high": BUY_GREEN, "medium": DEAD_ZONE, "low": LOSS_RED}


def render(data: CalibrationView | None) -> None:
    st.title("Calibration")
    if data is None:
        st.info("No data yet.")
        return

    st.caption(
        f"Auto-tune {'enabled' if data.auto_tune_enabled else 'disabled'} · "
        f"manual apply {'disabled' if data.auto_tune_enabled else 'enabled'}"
    )

    # Calibration table — proper HTML for dark theme.
    rows_html = "".join(
        f"""<tr style="border-top: 0.5px solid {BORDER};">
<td style="padding: 6px 10px;">{line.bucket}</td>
<td style="padding: 6px 10px;">{line.regime}</td>
<td style="padding: 6px 10px; text-align: right;">{line.n_closed}</td>
<td style="padding: 6px 10px; text-align: right;">{line.expectancy_R:+.2f}R</td>
<td style="padding: 6px 10px; text-align: right; color: {TEXT_TERTIARY};">
[{line.ci_low_R:+.2f}, {line.ci_high_R:+.2f}]</td>
<td style="padding: 6px 10px;">
<span class="plutus-pill" style="background:{SURFACE}; color:{_BAND_COLOR.get(line.confidence_band, TEXT_SECONDARY)};">
{line.confidence_band}</span></td>
<td style="padding: 6px 10px; color: {TEXT_TERTIARY}; font-size: 10px;">{line.sprt_state}</td>
</tr>"""
        for line in data.lines
    )
    st.markdown(
        f"""<div class="plutus-card" style="padding: 0;">
<table style="width: 100%; border-collapse: collapse; font-size: 12px; color: {TEXT_PRIMARY};">
<thead><tr style="color: {TEXT_TERTIARY}; font-size: 11px;">
<th style="padding: 8px 10px; text-align: left;">bucket</th>
<th style="padding: 8px 10px; text-align: left;">regime</th>
<th style="padding: 8px 10px; text-align: right;">n</th>
<th style="padding: 8px 10px; text-align: right;">expectancy R</th>
<th style="padding: 8px 10px; text-align: right;">CI (R)</th>
<th style="padding: 8px 10px; text-align: left;">band</th>
<th style="padding: 8px 10px; text-align: left;">SPRT</th>
</tr></thead><tbody>{rows_html or '<tr><td colspan=7 style="padding: 14px; text-align: center; color:' + TEXT_TERTIARY + '">no calibration data</td></tr>'}</tbody></table></div>""",
        unsafe_allow_html=True,
    )

    st.markdown("### Tuner proposals")
    if not data.proposals:
        st.caption("No active proposals.")
    for i, prop in enumerate(data.proposals):
        delta_color = BUY_GREEN if prop.delta_expectancy_R >= 0 else LOSS_RED
        st.markdown(
            f"""<div class="plutus-card">
<div style="font-size: 13px; color: {TEXT_PRIMARY};">
<b>{prop.bundle}</b> · {prop.regime} · {prop.parameter}</div>
<div style="font-size: 11px; color: {TEXT_SECONDARY}; margin: 4px 0;">
{prop.old_value} → {prop.proposed_value} ·
<span style="color:{delta_color}">Δ expectancy {prop.delta_expectancy_R:+.2f}R</span> ·
family-corrected p {prop.family_corrected_p:.3f}</div>""",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns([1, 4])
        if c1.button("Apply", key=f"apply_{i}", disabled=True):
            pass
        with c2:
            st.caption(
                "Manual apply not yet implemented — enable auto-tune to let the system apply approved proposals automatically."
            )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### Applied changes history")
    if st.button("Revert last", key="revert_last", disabled=True):
        pass
