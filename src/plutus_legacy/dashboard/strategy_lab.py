# src/plutus/dashboard/strategy_lab.py
"""Strategy Lab tab — backtest UI with error/warning states."""
from __future__ import annotations

import streamlit as st

from plutus.backtesting.runner import run_bundle, MIN_BARS_REQUIRED, BUNDLE_MAP
from plutus.data.ohlcv import InsufficientDataError


def render() -> None:
    st.header("Strategy Lab")

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("Symbol", value="RELIANCE").strip().upper()
    with col2:
        bundle = st.selectbox("Bundle", list(BUNDLE_MAP.keys()), index=0)
    with col3:
        days = st.number_input("Days", min_value=10, max_value=365, value=90, step=10)

    if st.button("Run Backtest", type="primary"):
        if not symbol:
            st.error("Enter a symbol.")
            return

        with st.spinner("Running backtest…"):
            try:
                result = run_bundle(symbol, bundle, days=int(days))
            except InsufficientDataError as e:
                st.error(
                    f"⛔ Insufficient data: only **{e.bars_fetched}** bars retrieved "
                    f"for **{e.symbol}**, minimum required is **{e.bars_required}**. "
                    f"Try a longer date range or a different symbol."
                )
                return
            except Exception as e:
                st.error(f"❌ Backtest failed: {e}")
                return

        # Warnings banner
        for w in result.warnings:
            st.warning(f"⚠️ {w}")

        if result.suspect:
            st.warning("🚩 Results flagged as suspect — review with caution.")

        if result.total_trades == 0:
            st.info(
                "ℹ️ No trades were generated for this symbol/bundle/period combination."
            )
            return

        # Metrics
        st.subheader("Results")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Win Rate", f"{result.win_rate * 100:.1f}%")
        c2.metric("Sharpe", f"{result.sharpe_ratio:.2f}")
        c3.metric("Avg Return", f"{result.avg_return_pct:.2f}%")
        c4.metric("Max Drawdown", f"{result.max_drawdown_pct:.2f}%")
        c5.metric("Trades", result.total_trades)

        # Trade log
        if result.trades:
            with st.expander("Trade Log", expanded=False):
                st.dataframe(result.trades, use_container_width=True)
