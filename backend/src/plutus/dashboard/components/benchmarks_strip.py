from __future__ import annotations

import streamlit as st

from plutus.shared.benchmarks.strip import BenchmarkResult


def benchmarks_strip(result: BenchmarkResult) -> None:
    """B2 — all four baselines, net of costs."""
    cols = st.columns(4)
    cols[0].metric("Plutus", f"{result.plutus_net_pct:.2f}%")
    cols[1].metric("Nifty B&H", f"{result.nifty_net_pct:.2f}%")
    cols[2].metric("Regime-switched", f"{result.regime_switched_net_pct:.2f}%")
    cols[3].metric("Random liquid", f"{result.random_liquid_net_pct:.2f}%")
    st.caption(
        f"profit factor {result.plutus_profit_factor:.2f} · n={result.plutus_n_trades}"
    )
