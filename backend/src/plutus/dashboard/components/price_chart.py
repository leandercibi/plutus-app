from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from plutus.dashboard.theme import (
    BORDER,
    BUY_GREEN,
    LOSS_RED,
    SWING_ACCENT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)

_BUNDLE_COLORS: dict[str, str] = {
    "trend": "#c69a4a",
    "breakout": "#5dcaa5",
    "reversal": "#e06a8a",
    "vcp": "#8aa9e0",
    "composite": "#a580d0",
    "bull_ready": BUY_GREEN,
}

_BUNDLE_LABELS: dict[str, str] = {
    "trend": "Trend — 50DMA pullback",
    "breakout": "Breakout — range expansion",
    "reversal": "Reversal — oversold bounce",
    "vcp": "VCP — volatility contraction",
    "composite": "Composite — multi-signal",
    "bull_ready": "Bull-ready — accumulation convert",
}

_DURATION_OPTIONS: list[tuple[str, int]] = [
    ("3d", 3),
    ("1w", 7),
    ("1m", 30),
    ("3m", 90),
    ("6m", 180),
    ("1y", 365),
]
_DEFAULT_DAYS = 300

_MACD_COLOR = "#e0c060"
_MACD_SIGNAL_COLOR = "#8aa9e0"
_BB_COLOR = "#a580d0"
_RIBBON_COLORS = ["#5dcaa5", "#6dbf8a", "#80b580", "#a0a070", "#c08a60"]
_CROSS_COLOR = BUY_GREEN


def _price_header(data: dict[str, Any]) -> None:
    price = data["latest_price"]
    change = data["latest_change_pct"]
    color = BUY_GREEN if change >= 0 else LOSS_RED
    arrow = "▲" if change >= 0 else "▼"
    st.markdown(
        f'<div style="font-size:20px;font-weight:500;color:{TEXT_PRIMARY};">'
        f"₹{price:,.2f} "
        f'<span style="font-size:13px;color:{color};">{arrow} {change:+.2f}%</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _bundle_badge(bundle: str) -> None:
    color = _BUNDLE_COLORS.get(bundle, TEXT_SECONDARY)
    label = _BUNDLE_LABELS.get(bundle, bundle.title())
    st.markdown(
        f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;'
        f'font-size:11px;font-weight:500;background:{color}22;color:{color};">'
        f"{label}</span>",
        unsafe_allow_html=True,
    )


def _add_bollinger_layers(
    df: pd.DataFrame,
    y_scale: alt.Scale,
    layers: list,
) -> None:
    bb_df = df[df["bb_upper"].notna()].copy()
    if bb_df.empty:
        return
    band = (
        alt.Chart(bb_df)
        .mark_area(opacity=0.08, color=_BB_COLOR)
        .encode(
            x="date:T",
            y=alt.Y("bb_upper:Q", scale=y_scale),
            y2="bb_lower:Q",
        )
    )
    upper = (
        alt.Chart(bb_df)
        .mark_line(strokeWidth=0.8, strokeDash=[3, 3], color=_BB_COLOR, opacity=0.5)
        .encode(x="date:T", y=alt.Y("bb_upper:Q", scale=y_scale))
    )
    lower = (
        alt.Chart(bb_df)
        .mark_line(strokeWidth=0.8, strokeDash=[3, 3], color=_BB_COLOR, opacity=0.5)
        .encode(x="date:T", y=alt.Y("bb_lower:Q", scale=y_scale))
    )
    layers.extend([band, upper, lower])


def _add_ema_ribbon_layers(
    df: pd.DataFrame,
    y_scale: alt.Scale,
    layers: list,
) -> None:
    ema_cols = ["ema8", "ema13", "ema21", "ema34", "ema55"]
    for i, col in enumerate(ema_cols):
        ema_df = df[df[col].notna()].copy()
        if ema_df.empty:
            continue
        line = (
            alt.Chart(ema_df)
            .mark_line(strokeWidth=0.9, color=_RIBBON_COLORS[i], opacity=0.6)
            .encode(x="date:T", y=alt.Y(f"{col}:Q", scale=y_scale))
        )
        layers.append(line)


def _add_golden_cross_markers(
    df: pd.DataFrame,
    y_scale: alt.Scale,
    layers: list,
) -> None:
    cross_df = df[df["golden_cross_20_50"] == True].copy()  # noqa: E712
    if cross_df.empty:
        return
    points = (
        alt.Chart(cross_df)
        .mark_point(
            shape="triangle-up",
            size=120,
            color=_CROSS_COLOR,
            filled=True,
            opacity=0.9,
        )
        .encode(
            x="date:T",
            y=alt.Y("close:Q", scale=y_scale),
        )
    )
    layers.append(points)


def render_price_chart(
    data: dict[str, Any],
    chart_key: str = "",
    fetch_fn: Callable[[int], dict | None] | None = None,
) -> None:
    key_prefix = chart_key or data.get("symbol", "chart")

    days_key = f"days_{key_prefix}"
    if days_key not in st.session_state:
        st.session_state[days_key] = _DEFAULT_DAYS

    dur_cols = st.columns(len(_DURATION_OPTIONS))
    for i, (label, days_val) in enumerate(_DURATION_OPTIONS):
        with dur_cols[i]:
            if st.button(
                label,
                key=f"dur_{key_prefix}_{label}",
                help=f"Show {label} of data",
                use_container_width=True,
            ):
                st.session_state[days_key] = days_val
                st.rerun()

    if f"chartdata_{key_prefix}" in st.session_state:
        data = st.session_state[f"chartdata_{key_prefix}"]

    current_days = st.session_state[days_key]
    intraday_raw = data.get("intraday_bars", [])
    use_intraday = current_days <= 7 and len(intraday_raw) > 0

    if use_intraday:
        cutoff = (date.today() - timedelta(days=current_days)).isoformat()
        bars = [b for b in intraday_raw if b["date"][:10] >= cutoff]
    else:
        all_daily = data.get("bars", [])
        bars = all_daily[-current_days:] if current_days < len(all_daily) else all_daily

    if not bars:
        st.caption("No chart data available.")
        return

    _price_header(data)

    marker = data.get("signal_marker")
    if marker:
        _bundle_badge(marker["bundle"])

    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["date"])

    # Use time-aware x-axis format for intraday views
    x_fmt = "%b %d %H:%M" if use_intraday else "%b %d"

    has_overlays = any(
        df.get(col) is not None and df[col].notna().any()
        for col in ["macd", "bb_upper", "ema8"]
        if col in df.columns
    )

    show_bb = False
    show_macd = False
    show_ribbon = False
    show_cross = False

    if has_overlays:
        tcols = st.columns(4)
        with tcols[0]:
            show_macd = st.toggle("MACD", key=f"tgl_macd_{key_prefix}")
        with tcols[1]:
            show_bb = st.toggle("Bollinger", key=f"tgl_bb_{key_prefix}")
        with tcols[2]:
            show_ribbon = st.toggle("EMA Ribbon", key=f"tgl_ribbon_{key_prefix}")
        with tcols[3]:
            show_cross = st.toggle("Golden Cross", key=f"tgl_cross_{key_prefix}")

    all_prices = df["close"].tolist()
    if show_bb and "bb_upper" in df.columns:
        bb_vals = df["bb_upper"].dropna().tolist() + df["bb_lower"].dropna().tolist()
        all_prices.extend(bb_vals)
    if marker:
        for lvl in ("entry", "stop_loss", "target_1", "target_2"):
            v = marker.get(lvl)
            if v is not None:
                all_prices.append(v)
    y_min = min(all_prices) * 0.97
    y_max = max(all_prices) * 1.03
    y_scale = alt.Scale(domain=[y_min, y_max], zero=False, clamp=True)

    x_axis = alt.X(
        "date:T",
        axis=alt.Axis(format=x_fmt, labelColor=TEXT_TERTIARY, gridColor=BORDER, title=None),
    )
    y_axis = alt.Y(
        "close:Q",
        scale=y_scale,
        axis=alt.Axis(labelColor=TEXT_TERTIARY, gridColor=BORDER, title=None),
    )

    close_line = (
        alt.Chart(df).mark_line(strokeWidth=1.5, color=TEXT_PRIMARY).encode(x=x_axis, y=y_axis)
    )

    layers: list = [close_line]

    if show_bb:
        _add_bollinger_layers(df, y_scale, layers)

    if show_ribbon:
        _add_ema_ribbon_layers(df, y_scale, layers)

    dma_specs = [
        ("dma20", "#e0c060", [4, 2], "20 DMA"),
        ("dma50", SWING_ACCENT, [], "50 DMA"),
        ("dma200", "#e06a8a", [6, 3], "200 DMA"),
    ]
    for col, color, dash, _label in dma_specs:
        dma_df = df[df[col].notna()].copy()
        if dma_df.empty:
            continue
        line = (
            alt.Chart(dma_df)
            .mark_line(strokeWidth=1.2, strokeDash=dash, color=color, opacity=0.7)
            .encode(x="date:T", y=alt.Y(f"{col}:Q", scale=y_scale))
        )
        layers.append(line)

    if show_cross:
        _add_golden_cross_markers(df, y_scale, layers)

    if marker:
        for level, color, label in [
            ("entry", BUY_GREEN, "Entry"),
            ("stop_loss", LOSS_RED, "Stop"),
            ("target_1", "#5dcaa5", "T1"),
            ("target_2", "#8aa9e0", "T2"),
        ]:
            val = marker.get(level)
            if val is None:
                continue
            rule_df = pd.DataFrame({"y": [val], "label": [f"{label} ₹{val:,.0f}"]})
            rule = (
                alt.Chart(rule_df)
                .mark_rule(strokeDash=[4, 3], strokeWidth=1.2, color=color, opacity=0.8)
                .encode(y="y:Q")
            )
            text = (
                alt.Chart(rule_df)
                .mark_text(align="left", dx=5, dy=-6, fontSize=10, color=color, fontWeight="bold")
                .encode(
                    y="y:Q",
                    x=alt.value(0),
                    text="label:N",
                )
            )
            layers.extend([rule, text])

    chart = (
        alt.layer(*layers)
        .properties(height=300)
        .configure_view(strokeWidth=0)
        .configure_axis(
            domainColor=BORDER,
            tickColor=BORDER,
        )
    )

    st.altair_chart(chart, use_container_width=True, theme=None)

    legend_parts = [
        f'<span style="color:{color};font-size:11px;">{"—" if not dash else "- -"} {label}</span>'
        for _, color, dash, label in dma_specs
    ]
    if show_bb:
        legend_parts.append(f'<span style="color:{_BB_COLOR};font-size:11px;">- - Bollinger</span>')
    if show_ribbon:
        legend_parts.append(
            f'<span style="color:{_RIBBON_COLORS[0]};font-size:11px;">— EMA Ribbon</span>'
        )
    if show_cross:
        legend_parts.append(
            f'<span style="color:{_CROSS_COLOR};font-size:11px;">▲ Golden Cross</span>'
        )
    st.markdown(
        f'<div style="font-size:11px;color:{TEXT_TERTIARY};margin-top:-10px;">'
        f"{' · '.join(legend_parts)}</div>",
        unsafe_allow_html=True,
    )

    if show_macd and "macd" in df.columns:
        macd_df = df[df["macd"].notna()].copy()
        if not macd_df.empty:
            macd_line = (
                alt.Chart(macd_df)
                .mark_line(strokeWidth=1.2, color=_MACD_COLOR)
                .encode(
                    x=alt.X(
                        "date:T",
                        axis=alt.Axis(
                            format=x_fmt, labelColor=TEXT_TERTIARY, gridColor=BORDER, title=None
                        ),
                    ),
                    y=alt.Y(
                        "macd:Q",
                        axis=alt.Axis(labelColor=TEXT_TERTIARY, gridColor=BORDER, title=None),
                    ),
                )
            )
            signal_line = (
                alt.Chart(macd_df)
                .mark_line(strokeWidth=1.0, strokeDash=[4, 2], color=_MACD_SIGNAL_COLOR)
                .encode(x="date:T", y="macd_signal:Q")
            )
            hist_pos = macd_df[macd_df["macd_hist"] >= 0]
            hist_neg = macd_df[macd_df["macd_hist"] < 0]
            hist_layers = [macd_line, signal_line]
            if not hist_pos.empty:
                hist_layers.append(
                    alt.Chart(hist_pos)
                    .mark_bar(color=BUY_GREEN, opacity=0.4)
                    .encode(x="date:T", y="macd_hist:Q")
                )
            if not hist_neg.empty:
                hist_layers.append(
                    alt.Chart(hist_neg)
                    .mark_bar(color=LOSS_RED, opacity=0.4)
                    .encode(x="date:T", y="macd_hist:Q")
                )
            macd_chart = (
                alt.layer(*hist_layers)
                .properties(height=100)
                .configure_view(strokeWidth=0)
                .configure_axis(domainColor=BORDER, tickColor=BORDER)
            )
            st.altair_chart(macd_chart, use_container_width=True, theme=None)
            st.markdown(
                f'<div style="font-size:11px;color:{TEXT_TERTIARY};margin-top:-10px;">'
                f'<span style="color:{_MACD_COLOR};">— MACD</span> · '
                f'<span style="color:{_MACD_SIGNAL_COLOR};">- - Signal</span> · '
                f'<span style="color:{BUY_GREEN};">■</span>/<span style="color:{LOSS_RED};">■</span> Histogram'
                f"</div>",
                unsafe_allow_html=True,
            )
