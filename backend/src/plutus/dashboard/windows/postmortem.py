from __future__ import annotations

import streamlit as st

from plutus.dashboard.components.benchmarks_strip import benchmarks_strip
from plutus.dashboard.data import PostmortemView


def render(data: PostmortemView) -> None:
    """Weekly postmortem (spec 14 §9). B2 — benchmark strip. C5 — no naked win rate."""
    if data is None:
        st.info("No data yet.")
        return
    st.title("Postmortem")
    if data.available_weeks:
        st.selectbox("Week ending", options=data.available_weeks, index=0)
    else:
        st.caption("No postmortem weeks yet.")

    # B2: all four baselines, net of costs.
    benchmarks_strip(data.benchmarks)

    st.markdown("**Per-bundle pull-throughs**")
    # C5: every win-rate cell is paired with an adjacent CI cell — no naked win rate.
    st.markdown("| bundle | n | win rate | CI (R) | expectancy R |")
    st.markdown("|---|---|---|---|---|")
    for row in data.bundle_rows:
        st.markdown(
            f"| {row.bundle} | {row.n_trades} | {row.win_rate:.1%} | "
            f"[{row.ci_low_R:.2f}, {row.ci_high_R:.2f}] | {row.expectancy_R:.2f}R |"
        )

    st.caption(
        f"WRONG_DIRECTION {data.wrong_direction_count} · "
        f"no-progress scratches {data.no_progress_count}"
    )

    if data.slippage_divergence_bps is not None:
        st.markdown(f"Slippage divergence (mock vs real): {data.slippage_divergence_bps:.1f} bps")
