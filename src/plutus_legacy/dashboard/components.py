"""Shared UI components for the Plutus dashboard."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from plutus.data.ohlcv import fetch_ohlcv, add_indicators


def render_stock_chart(symbol: str, days: int = 60) -> None:
    """Candlestick + EMA21/EMA50 chart."""
    try:
        fetch_days = max(days, 90)
        df = add_indicators(fetch_ohlcv(symbol, days=fetch_days))
        df = df.tail(days)
        fig = go.Figure()
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name=symbol,
            )
        )
        if "EMA_21" in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["EMA_21"],
                    name="EMA21",
                    line=dict(color="blue", width=1),
                )
            )
        if "EMA_50" in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["EMA_50"],
                    name="EMA50",
                    line=dict(color="orange", width=1.5),
                )
            )
        fig.update_layout(
            title=f"{symbol} — {days}-day chart",
            xaxis_rangeslider_visible=False,
            height=420,
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        st.caption(f"Chart unavailable for {symbol}.")
