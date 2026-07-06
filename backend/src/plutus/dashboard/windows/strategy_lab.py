from __future__ import annotations

import streamlit as st

from plutus.dashboard.api_client import fetch_chart_data
from plutus.dashboard.backtest_service import (
    BUNDLE_FACTORIES,
    run_single_symbol_backtest,
)
from plutus.dashboard.components.benchmarks_strip import benchmarks_strip
from plutus.dashboard.components.price_chart import render_price_chart
from plutus.dashboard.data import StrategyLabView
from plutus.dashboard.theme import (
    ACCUMULATION_ACCENT,
    BUY_GREEN,
    DEAD_ZONE,
    DEAD_ZONE_BG,
    LOSS_RED,
    SURFACE,
    SWING_ACCENT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)

_SWING_LABEL_COLORS = {
    "BUY": BUY_GREEN,
    "BUY_WATCH": "#f0a500",
    "WATCH": TEXT_SECONDARY,
    "HOLD": TEXT_TERTIARY,
    "AVOID": LOSS_RED,
}
_ACCUM_LABEL_COLORS = {
    "ACCUMULATE_NOW": BUY_GREEN,
    "BUILD_SLOWLY": "#f0a500",
    "WATCH": TEXT_SECONDARY,
    "AVOID": LOSS_RED,
}


def _run_quick_score(symbol: str) -> None:
    from datetime import date, timedelta

    from plutus.data.providers.yfinance_provider import YFinanceProvider
    from plutus.swing.scoring.pillars import technical_score

    provider = YFinanceProvider()
    end = date.today()
    start = end - timedelta(days=400)
    try:
        candles = provider.fetch(symbol, start, end)
    except Exception as exc:
        st.session_state[f"qs_{symbol}"] = {"error": str(exc)}
        return

    if candles is None or len(candles) < 30:
        st.session_state[f"qs_{symbol}"] = {"error": "Not enough price data"}
        return

    result: dict = {"symbol": symbol}

    try:
        tech = technical_score(candles)
        close = candles["close"]
        price = float(close.iloc[-1])
        dma50 = float(close.rolling(50).mean().iloc[-1])
        dma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else dma50
        above_50 = price > dma50
        above_200 = price > dma200

        swing_score = tech.total
        if swing_score >= 22:
            swing_label = "BUY"
        elif swing_score >= 16:
            swing_label = "BUY_WATCH"
        elif swing_score >= 10:
            swing_label = "WATCH"
        else:
            swing_label = "AVOID"

        result["swing"] = {
            "score": swing_score,
            "label": swing_label,
            "trend_momentum": round(tech.trend_momentum, 1),
            "atr_percentile": round(tech.atr_percentile, 1),
            "mean_reversion": round(tech.mean_reversion, 1),
            "macd_cross_bonus": round(tech.macd_cross_bonus, 1),
            "bb_squeeze_bonus": round(tech.bollinger_squeeze_bonus, 1),
            "above_50dma": above_50,
            "above_200dma": above_200,
        }
    except Exception as exc:
        result["swing_error"] = str(exc)

    try:
        from plutus.accumulation.rs.blend import RSBlend

        rs_engine = RSBlend()
        nifty = provider.fetch("^NSEI", start, end)
        if nifty is not None and len(nifty) >= 181 and len(candles) >= 200:
            rs = rs_engine.compute(candles, nifty)
            rs_blended = rs.blended
            rs_30 = rs.rs_30
            rs_90 = rs.rs_90
            rs_180 = rs.rs_180
        else:
            rs_blended = rs_30 = rs_90 = rs_180 = 0.0

        quality_score = min(30, max(0, tech.total))
        from plutus.accumulation.fundamentals.hard_avoid import HardAvoidResult
        from plutus.accumulation.scoring.classifier import AccumulationClassifier
        from plutus.accumulation.scoring.pillars import compose_pillars

        pillars = compose_pillars(quality_score, 12, 15, rs_blended)
        accum_label = AccumulationClassifier().classify(
            pillar_score=pillars.total,
            quality_score=pillars.quality,
            hard_avoid=HardAvoidResult(avoid=False, reasons=[]),
        )
        result["accum"] = {
            "score": pillars.total,
            "label": accum_label,
            "quality": pillars.quality,
            "growth": pillars.growth,
            "valuation": pillars.valuation,
            "rs": pillars.relative_strength,
            "rs_30": round(rs_30 * 100, 1),
            "rs_90": round(rs_90 * 100, 1),
            "rs_180": round(rs_180 * 100, 1),
        }
    except Exception as exc:
        result["accum_error"] = str(exc)

    st.session_state[f"qs_{symbol}"] = result


def _render_quick_score(symbol: str) -> None:
    result = st.session_state.get(f"qs_{symbol}")
    if result is None:
        return

    if "error" in result:
        st.error(f"Scoring failed: {result['error']}")
        return

    st.markdown("#### Quick score results")
    col_s, col_a = st.columns(2)

    with col_s:
        st.markdown(
            f'<div style="font-size:12px;color:{TEXT_TERTIARY};margin-bottom:4px;">Swing (technical only)</div>',
            unsafe_allow_html=True,
        )
        if "swing" in result:
            sw = result["swing"]
            label_color = _SWING_LABEL_COLORS.get(sw["label"], TEXT_SECONDARY)
            st.markdown(
                f'<div style="font-size:28px;font-weight:500;color:{SWING_ACCENT};">{sw["score"]}<span style="font-size:14px;color:{TEXT_TERTIARY}">/30</span></div>'
                f'<div style="font-size:13px;font-weight:500;color:{label_color};margin-bottom:8px;">{sw["label"]}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="font-size:12px;color:{TEXT_SECONDARY};line-height:1.8;">'
                f"Trend momentum: <b>{sw['trend_momentum']}</b> · ATR rank: <b>{sw['atr_percentile']}</b><br>"
                f"Mean reversion: <b>{sw['mean_reversion']}</b> · MACD cross: <b>+{sw['macd_cross_bonus']}</b> · BB squeeze: <b>+{sw['bb_squeeze_bonus']}</b><br>"
                f"Above 50 DMA: {'✓' if sw['above_50dma'] else '✗'} · Above 200 DMA: {'✓' if sw['above_200dma'] else '✗'}"
                f"</div>",
                unsafe_allow_html=True,
            )
        elif "swing_error" in result:
            st.caption(f"Swing error: {result['swing_error']}")

    with col_a:
        st.markdown(
            f'<div style="font-size:12px;color:{TEXT_TERTIARY};margin-bottom:4px;">Accumulation (tech + RS; fundamentals not fetched)</div>',
            unsafe_allow_html=True,
        )
        if "accum" in result:
            ac = result["accum"]
            label_color = _ACCUM_LABEL_COLORS.get(ac["label"], TEXT_SECONDARY)
            st.markdown(
                f'<div style="font-size:28px;font-weight:500;color:{ACCUMULATION_ACCENT};">{ac["score"]}<span style="font-size:14px;color:{TEXT_TERTIARY}">/100</span></div>'
                f'<div style="font-size:13px;font-weight:500;color:{label_color};margin-bottom:8px;">{ac["label"]}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="font-size:12px;color:{TEXT_SECONDARY};line-height:1.8;">'
                f"Quality: <b>{ac['quality']}/30</b> · Growth: <b>{ac['growth']}/25</b> · "
                f"Valuation: <b>{ac['valuation']}/30</b> · RS: <b>{ac['rs']}/15</b><br>"
                f"RS vs Nifty — 30d: <b>{ac['rs_30']:+.1f}%</b> · 90d: <b>{ac['rs_90']:+.1f}%</b> · 180d: <b>{ac['rs_180']:+.1f}%</b>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.caption(
                "Note: Quality pillar here uses technical score as proxy. Full accumulation scoring requires fundamentals (PE, D/E, EPS history) which are fetched during the Sunday pipeline run."
            )
        elif "accum_error" in result:
            st.caption(f"Accum error: {result['accum_error']}")


def render(data: StrategyLabView) -> None:
    """Strategy lab (spec 14 §11). C3 — SMC shown display-only, not in live seeding."""
    if data is None:
        st.info("No data yet.")
        return
    st.title("Strategy lab")
    st.caption(
        "Single-symbol single-bundle screening. Display-only — not evidence for live sizing."
    )

    st.markdown(
        f"""<div style="background:{DEAD_ZONE_BG}; border-left: 2px solid {DEAD_ZONE};
padding: 10px 14px; border-radius: 4px; margin: 8px 0 14px; font-size: 11px; color: {DEAD_ZONE};">
<b>Use this for:</b> cross-bundle comparison on one symbol, cross-symbol comparison
of one bundle, spotting bundles that consistently blow up.<br>
<b>Do NOT use for sizing.</b> Results are in-sample, single-regime (SIDEWAYS stub),
single-symbol, and use the synthetic delivery stub — small-n win rates are not
calibrated. Live evidence comes from the postmortem (spec 15 go-live bar).
</div>""",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    bundle = c1.selectbox("Bundle", options=data.available_bundles, key="lab_bundle")
    if not data.available_symbols:
        c2.selectbox(
            "Symbol",
            options=["(universe empty — add scripts/nse500.csv)"],
            disabled=True,
            key="lab_symbol_empty",
        )
        symbol = None
    else:
        symbol = c2.selectbox(
            f"Symbol ({len(data.available_symbols)} in universe)",
            options=data.available_symbols,
            key="lab_symbol",
        )

    if symbol is not None:
        if st.button(
            "⚡ Quick score",
            key="lab_quick_score",
            help="Compute swing + accumulation score for this symbol",
        ):
            with st.spinner(f"Scoring {symbol}…"):
                _run_quick_score(symbol)

        _render_quick_score(symbol)

    o1, o2 = st.columns(2)
    use_costs = o1.checkbox("Cost model", value=True, key="lab_costs")
    use_fills = o2.checkbox("Fill policy", value=True, key="lab_fills")

    lookback = st.slider("Lookback (days)", 90, 730, 365, step=30, key="lab_lookback")

    bundle_supported = bundle in BUNDLE_FACTORIES
    run = st.button(
        "▶ Run backtest",
        key="run_backtest",
        type="primary",
        disabled=(symbol is None or not bundle_supported),
        use_container_width=False,
    )
    if not bundle_supported and symbol is not None:
        gated_reason = {
            "pead": "Gated by spec **C2** — paper-only until verified earnings calendar "
            "+ one earnings season with the cost model proves net positive.",
            "smc": "Gated by spec **C3** — excluded from live seeding until pooled OOS "
            "per-regime evidence justifies the slot.",
        }.get(bundle, f"{bundle} not wired into the inline lab.")
        st.caption(gated_reason)

    if run and symbol is not None and bundle_supported:
        with st.spinner(f"Running {bundle} on {symbol} · {lookback}d…"):
            try:
                summary = run_single_symbol_backtest(bundle, symbol, lookback, use_costs, use_fills)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Backtest failed: {exc}")
            else:
                st.session_state["lab_last_run"] = summary

    summary = st.session_state.get("lab_last_run")
    if summary is not None:
        st.markdown(
            f"### Result · {summary.bundle} on {summary.symbol} · "
            f"{summary.start.isoformat()} → {summary.end.isoformat()}"
        )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Trades", summary.n_trades)
        m2.metric("Win rate", f"{summary.win_rate * 100:.1f}%" if summary.n_trades else "—")
        m3.metric(
            "Expectancy",
            f"{summary.expectancy_R:+.2f}R" if summary.n_trades else "—",
        )
        m4.metric("Sum R", f"{summary.sum_R:+.2f}R" if summary.n_trades else "—")
        if summary.n_trades == 0:
            st.info(
                "No trades produced. Either the bundle never fit a signal in the window, "
                "or every signal was filtered out by the fill policy."
            )
        else:
            st.caption(
                f"Avg hold {summary.avg_hold_days:.1f} days · "
                f"lookahead violations {summary.fills_before_signal} · "
                f"costs={'on' if summary.cost_model_on else 'off'} · "
                f"fills={'on' if summary.fill_policy_on else 'off'}"
            )
            st.dataframe(
                summary.trades_df,
                use_container_width=True,
                hide_index=True,
            )

        # Price chart for the backtested symbol
        chart_key = f"lab_chart_{summary.symbol}"
        if st.button("📈 Price chart", key=f"btn_{chart_key}"):
            st.session_state[chart_key] = True
            st.session_state.pop(f"chartdata_{chart_key}", None)
        if st.session_state.get(chart_key):
            if f"chartdata_{chart_key}" not in st.session_state:
                with st.spinner(f"Loading {summary.symbol} chart…"):
                    chart_data = fetch_chart_data(summary.symbol)
                if chart_data:
                    st.session_state[f"chartdata_{chart_key}"] = chart_data
                else:
                    st.warning("Could not load chart — is the API running?")
            chart_data = st.session_state.get(f"chartdata_{chart_key}")
            if chart_data:
                render_price_chart(chart_data, chart_key=chart_key)

    if data.last_run_benchmarks is not None:
        st.markdown("### Last run · benchmarks (net of costs)")
        benchmarks_strip(data.last_run_benchmarks)

    if data.last_run_stats:
        st.markdown("### Per-bundle stats")
        for stat in data.last_run_stats:
            st.markdown(
                f"<div style='background:{SURFACE}; padding: 8px 12px; "
                f"border-radius: 4px; margin-bottom: 4px; font-size: 12px; "
                f"color: {TEXT_PRIMARY};'>"
                f"<b>{stat.bundle}</b> · OOS shrunk Sharpe "
                f"<b>{stat.oos_sharpe_shrunk:.2f}</b> · "
                f"expectancy <b>{stat.expectancy_R:.2f}R</b> · "
                f"<span style='color:{TEXT_TERTIARY}'>n={stat.n_trades}</span></div>",
                unsafe_allow_html=True,
            )

    # --- Walk-Forward (4B) ---
    st.divider()
    st.markdown("### Walk-Forward")
    st.caption(
        "IS (70 %) / OOS (30 %) rolling windows. "
        "Overfit flag fires when OOS Sharpe drops > 50 % vs IS in ≥ 50 % of windows."
    )

    _WF_BUNDLES = [b for b in data.available_bundles if b not in ("composite", "smc")]
    wf_c1, wf_c2 = st.columns(2)
    wf_bundle = wf_c1.selectbox("WF Bundle", options=_WF_BUNDLES or ["trend"], key="wf_bundle")
    if data.available_symbols:
        wf_symbol = wf_c2.selectbox(
            f"WF Symbol ({len(data.available_symbols)} in universe)",
            options=data.available_symbols,
            key="wf_symbol",
        )
    else:
        wf_c2.selectbox("WF Symbol", options=["(empty)"], disabled=True, key="wf_symbol_empty")
        wf_symbol = None

    wf_n1, wf_n2 = st.columns(2)
    wf_window = wf_n1.number_input("Window (bars)", min_value=10, value=30, step=5, key="wf_window")
    wf_step = wf_n2.number_input("Step (bars)", min_value=1, value=7, step=1, key="wf_step")

    run_wf = st.button(
        "▶ Run Walk-Forward",
        key="run_walkforward",
        disabled=wf_symbol is None,
    )
    if run_wf and wf_symbol is not None:
        from plutus.backtesting.walk_forward import walk_forward as _wf

        with st.spinner(f"Running walk-forward for {wf_symbol} · {wf_bundle}…"):
            try:
                _wf_result = _wf(wf_symbol, wf_bundle, int(wf_window), int(wf_step))
            except Exception as exc:  # noqa: BLE001
                st.error(f"Walk-forward failed: {exc}")
            else:
                st.session_state["wf_last_run"] = _wf_result

    _wf_last = st.session_state.get("wf_last_run")
    if _wf_last is not None:
        import pandas as _pd

        wm1, wm2, wm3, wm4 = st.columns(4)
        wm1.metric("Windows", len(_wf_last.windows))
        wm2.metric("IS Sharpe (median)", f"{_wf_last.is_sharpe_median:.2f}")
        wm3.metric("OOS Sharpe (median)", f"{_wf_last.oos_sharpe_median:.2f}")
        wm4.metric("Overfit", "⚠ YES" if _wf_last.overfit_flag else "✓ No")
        if _wf_last.windows:
            _df = _pd.DataFrame(
                [
                    {
                        "Window": i + 1,
                        "IS Sharpe": round(w.is_sharpe, 3),
                        "OOS Sharpe": round(w.oos_sharpe, 3),
                        "IS Trades": w.is_trades,
                        "OOS Trades": w.oos_trades,
                    }
                    for i, w in enumerate(_wf_last.windows)
                ]
            )
            st.dataframe(_df, use_container_width=True, hide_index=True)

    # C3: SMC is display-only until pooled OOS per-regime evidence justifies it.
    if data.smc_display_only:
        st.markdown(
            f"<div style='background:{DEAD_ZONE_BG}; border-left: 2px solid {DEAD_ZONE}; "
            f"padding: 10px 14px; border-radius: 4px; font-size: 12px; color: {DEAD_ZONE};'>"
            "<b>SMC</b> — not in live seeding (display-only until pooled OOS evidence justifies it). "
            "Spec ref: C3.</div>",
            unsafe_allow_html=True,
        )
