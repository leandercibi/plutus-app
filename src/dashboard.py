# src/dashboard.py — top-level structure

import os
import time
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import func

from plutus.config import settings
from plutus.db.session import SessionLocal
from plutus.db.models import (
    BacktestResult,
    MockPortfolio,
    NewsEvent,
    PaperTrade,
    Recommendation,
    RejectedHeadline,
    TradeStatus,
    Watchlist,
    WeeklyRun,
)
from plutus.data.ohlcv import fetch_ohlcv, fetch_live_price, add_indicators

API_BASE = f"http://127.0.0.1:{settings.API_PORT}"  # default http://127.0.0.1:8000 — /analyze goes through cache + rate limit
API_KEY = settings.API_SECRET_KEY  # local API key for self-calls

st.set_page_config(
    page_title="Plutus — Indian Equities Recommendation Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

tabs = st.tabs(
    [
        "🏠 Home",
        "📊 Signals",
        "💼 Portfolio",
        "🧪 Strategy Lab",
        "📰 News Feed",
        "👁 Watchlist",
        "📋 History",
        "⚙️ Settings",
    ]
)

# ── Helper Functions ──────────────────────────────────────────────────────

from plutus.dashboard.helpers import drop_empty_revalidation as _drop_empty_revalidation


def _get_latest_recs(db, run_id: int) -> List[Recommendation]:
    return (
        db.query(Recommendation)
        .filter(Recommendation.weekly_run_id == run_id)
        .order_by(Recommendation.confidence.desc())
        .all()
    )


def _get_portfolio_data(name: str) -> Dict[str, Any]:
    from plutus.backtesting.paper_trader import PaperTrader

    return PaperTrader(name).get_summary()


from plutus.dashboard.portfolio_helpers import get_trade_history as _get_trade_history


def _render_stock_chart(symbol: str, days: int = 60) -> None:
    """Candlestick + EMA21/EMA50."""
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


from plutus.dashboard.analyze_card import (
    render_analyze_card as _analyze_card,
    render_analyze_result as _render_analyze_result_impl,
)


def _render_analyze_result(symbol: str, exchange: str = "NSE") -> None:
    """POST /analyze through the cached + rate-limited API."""
    _render_analyze_result_impl(symbol, exchange, API_BASE, API_KEY)


def _suggest_keyword(headline: str) -> str:
    """Heuristic: pick the longest non-stopword token from the headline."""
    stop = {"the", "and", "for", "with", "from", "this", "that", "into", "over"}
    tokens = [t.strip(".,:;!?\"'()") for t in headline.lower().split()]
    cands = [t for t in tokens if len(t) > 4 and t not in stop]
    return max(cands, key=len) if cands else "ADD-KEYWORD"


def _quarter_key(d: date) -> str:
    return f"{d.year}-Q{((d.month - 1) // 3) + 1}"


def _outcome_stats_for_run(run_id: int) -> Dict[str, int]:
    from plutus.db.models import OutcomeVerdict

    with SessionLocal() as db:
        rows = (
            db.query(Recommendation.outcome, func.count(Recommendation.id))
            .filter(Recommendation.weekly_run_id == run_id)
            .group_by(Recommendation.outcome)
            .all()
        )
    out = {"HIT_T1": 0, "HIT_T2": 0, "STOPPED": 0, "EXPIRED": 0, "PENDING": 0}
    for verdict, count in rows:
        key = verdict.value if hasattr(verdict, "value") else (verdict or "PENDING")
        out[key] = out.get(key, 0) + count
    out["closed"] = out["HIT_T1"] + out["HIT_T2"] + out["STOPPED"] + out["EXPIRED"]
    return out


def _render_history_drilldown(run: WeeklyRun) -> None:
    """Markdown body + recs table + outcomes summary + equity curve for this run."""
    # 1. Markdown body
    path = os.path.join(settings.REPORTS_DIR, f"{run.run_date}.md")
    if os.path.exists(path):
        with open(path) as f:
            st.markdown(f.read())
    else:
        st.caption(f"Report file `{path}` not present on disk.")

    # 2. Recommendations table
    with SessionLocal() as db:
        recs = (
            db.query(Recommendation)
            .filter(Recommendation.weekly_run_id == run.id)
            .order_by(Recommendation.confidence.desc())
            .all()
        )
    if recs:
        rec_df = pd.DataFrame(
            [
                {
                    "Symbol": r.symbol,
                    "Signal": r.recommendation.value,
                    "Score": r.confidence,
                    "Entry Mid": r.entry_mid,
                    "T1": r.target1,
                    "Stop": r.stop_loss,
                    "Outcome": r.outcome.value if r.outcome else "PENDING",
                    "P&L %": r.outcome_pct,
                    "Exit Date": r.outcome_exit_date,
                }
                for r in recs
            ]
        )
        st.subheader("Recommendations")
        st.dataframe(rec_df, use_container_width=True, hide_index=True)

    # 3. Outcomes summary card
    stats = _outcome_stats_for_run(run.id)
    closed_pcts = [r.outcome_pct for r in recs if r.outcome_pct is not None]
    avg_pnl = sum(closed_pcts) / len(closed_pcts) if closed_pcts else 0.0
    cs = st.columns(6)
    cs[0].metric("HIT_T1", stats["HIT_T1"])
    cs[1].metric("HIT_T2", stats["HIT_T2"])
    cs[2].metric("STOPPED", stats["STOPPED"])
    cs[3].metric("EXPIRED", stats["EXPIRED"])
    cs[4].metric("PENDING", stats["PENDING"])
    cs[5].metric("Avg P&L %", f"{avg_pnl:.2f}")

    # 4. Equity curve — cumulative pnl% across closed recs from this run
    closed = [r for r in recs if r.outcome_pct is not None and r.outcome_exit_date]
    if closed:
        closed.sort(key=lambda r: r.outcome_exit_date)
        eq = pd.DataFrame(
            {
                "exit_date": [r.outcome_exit_date for r in closed],
                "pnl_pct": [r.outcome_pct for r in closed],
            }
        )
        eq["cum_pnl_pct"] = eq["pnl_pct"].cumsum()
        fig = px.line(
            eq,
            x="exit_date",
            y="cum_pnl_pct",
            title="Cumulative P&L % (closed recs from this run)",
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig, use_container_width=True)


def _redacted_env_summary() -> Dict[str, Any]:
    """Show env-derived settings, redacting anything that looks like a secret."""
    secret_keys = {
        "API_KEY",
        "API_SECRET_KEY",
        "OPENROUTER_API_KEY",
        "DEEPSEEK_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "NEWS_API_KEY",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_CLIENT_ID",
        "DB_PASSWORD",
        "WHATSAPP_API_KEY",
    }
    out: Dict[str, Any] = {}
    for field in settings.model_fields:  # pydantic-settings v2
        val = getattr(settings, field)
        if field in secret_keys and val:
            out[field] = "***"
        else:
            out[field] = val
    return out


def _service_status() -> Dict[str, str]:
    """systemctl is-active for each plutus-* unit; falls back to 'unknown'."""
    import subprocess

    units = [
        "plutus-main.service",
        "plutus-bot.service",
        "plutus-dashboard.service",
        "postgresql.service",
    ]
    out: Dict[str, str] = {}
    for u in units:
        try:
            r = subprocess.run(
                ["systemctl", "is-active", u],
                capture_output=True,
                text=True,
                timeout=2,
            )
            out[u] = (r.stdout or r.stderr).strip() or "unknown"
        except Exception:
            out[u] = "unknown"
    return out


# ── Tab Implementations ───────────────────────────────────────────────────

with tabs[0]:
    st.title("📈 Plutus — Weekly Picks")
    st.caption(f"Loaded: {datetime.now().strftime('%d %b %Y %H:%M')} IST")

    with SessionLocal() as db:
        latest_run = db.query(WeeklyRun).order_by(WeeklyRun.id.desc()).first()
        if not latest_run:
            st.info("No weekly analysis yet. Next run: Sunday 18:00 IST.")

        if st.button("▶️ Run Weekly Analysis Now", type="primary"):
            with st.spinner("Triggering pipeline…"):
                try:
                    with httpx.Client(timeout=10.0) as cli:
                        r = cli.post(
                            f"{API_BASE}/pipeline/run",
                            headers={"X-API-Key": API_KEY},
                        )
                    if r.status_code == 409:
                        st.warning("Pipeline is already running.")
                    elif r.status_code in (200, 202):
                        st.success(
                            "Pipeline started. Results will appear after completion."
                        )
                    else:
                        st.error(f"Failed to start pipeline: {r.status_code} {r.text}")
                except Exception as e:
                    st.error(f"Could not reach API: {e}")

        if latest_run:
            recs = _get_latest_recs(db, latest_run.id)
            buy = [r for r in recs if r.recommendation.value == "BUY"]
            watch = [r for r in recs if r.recommendation.value == "WATCH"]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Run Date", str(latest_run.run_date))
            c2.metric("Market Regime", latest_run.market_regime or "N/A")
            c3.metric("BUY Signals", len(buy))
            c4.metric("WATCH Signals", len(watch))

            st.divider()
            st.subheader("Top BUY Picks")
            for rec in buy[:5]:
                with st.expander(
                    f"✅ {rec.symbol} — score {rec.confidence:.1f}/10 "
                    f"(R:R {rec.rr_ratio:.2f})"
                ):
                    cc1, cc2, cc3, cc4 = st.columns(4)
                    cc1.metric("Entry", f"₹{rec.entry_low:.0f}–{rec.entry_high:.0f}")
                    cc2.metric("Target 1", f"₹{rec.target1:.0f}")
                    cc3.metric("Stop Loss", f"₹{rec.stop_loss:.0f}")
                    cc4.metric(
                        "Hold",
                        f"{rec.hold_days_min or 5}–{rec.hold_days_max or 10}d",
                    )
                    if rec.revalidation_note:
                        st.warning(f"Monday revalidation: {rec.revalidation_note}")
                    st.write(rec.reasoning_text)
                    if st.button(
                        f"🔄 Run /analyze for {rec.symbol}", key=f"home_an_{rec.id}"
                    ):
                        _render_analyze_result(rec.symbol, rec.exchange or "NSE")
with tabs[1]:
    st.title("📊 Signal Board")

    with SessionLocal() as db:
        latest_run = db.query(WeeklyRun).order_by(WeeklyRun.id.desc()).first()
        if not latest_run:
            st.info("No data yet.")
        else:
            # ── Top-of-page regime badges ────────────────────────────────
            reg_color = {"BULLISH": "🟢", "BEARISH": "🔴", "SIDEWAYS": "🟡"}.get(
                latest_run.market_regime or "", "⚪"
            )
            b1, b2, b3, b4 = st.columns(4)
            b1.metric(
                "Nifty Regime", f"{reg_color} {latest_run.market_regime or 'N/A'}"
            )
            b2.metric("Nifty Trend", latest_run.nifty_trend or "N/A")
            b3.metric("BUY Signals", latest_run.total_buy_signals or 0)
            b4.metric("WATCH Signals", latest_run.total_watch_signals or 0)
            st.divider()

            recs = (
                db.query(Recommendation)
                .filter(Recommendation.weekly_run_id == latest_run.id)
                .order_by(Recommendation.confidence.desc())
                .all()
            )

            rows: List[Dict[str, Any]] = []
            for r in recs:
                # ── Derived distance columns ─────────────────────────
                entry_mid = float(r.entry_mid) if r.entry_mid else None
                sl = float(r.stop_loss) if r.stop_loss else None
                t1 = float(r.target1) if r.target1 else None
                t2 = float(r.target2) if r.target2 else None
                sl_dist = (
                    round((entry_mid - sl) / entry_mid * 100, 2)
                    if entry_mid and sl and entry_mid > 0
                    else None
                )
                t1_dist = (
                    round((t1 - entry_mid) / entry_mid * 100, 2)
                    if entry_mid and t1 and entry_mid > 0
                    else None
                )

                rows.append(
                    {
                        "Symbol": r.symbol,
                        "Signal": r.recommendation.value,
                        "Score /10": r.confidence,
                        "Tech": r.technical_score,
                        "Sent": r.sentiment_score,
                        "SmMny": r.smart_money_score,
                        "Regime": r.regime_score,
                        "R:R score": r.rr_score,
                        "Entry Mid": entry_mid,
                        "SL": sl,
                        "SL dist%": sl_dist,
                        "T1": t1,
                        "T1 dist%": t1_dist,
                        "T2": t2,
                        "R:R": r.rr_ratio,
                        "Hold (min)": r.hold_days_min,
                        "Hold (max)": r.hold_days_max,
                        "Strategy": r.strategy_used,
                        "Revalidation": r.revalidation_note or "",
                        "Outcome": r.outcome.value if r.outcome else "PENDING",
                    }
                )
            df = pd.DataFrame(rows)

            signal_filter = st.multiselect(
                "Filter by signal",
                ["BUY", "WATCH", "HOLD", "AVOID"],
                default=["BUY", "WATCH"],
            )
            if signal_filter and not df.empty:
                df = df[df["Signal"].isin(signal_filter)]

            # Hide the Revalidation column entirely if no row has one.
            df = _drop_empty_revalidation(df)

            # ── Sub-score visibility toggle ──────────────────────────
            show_sub = st.checkbox(
                "Show sub-score pillars", value=False, key="sig_show_sub"
            )
            display_df = df.copy()
            if not show_sub:
                display_df = display_df.drop(
                    columns=[
                        c
                        for c in ["Tech", "Sent", "SmMny", "Regime", "R:R score"]
                        if c in display_df.columns
                    ],
                    errors="ignore",
                )

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Score /10": st.column_config.ProgressColumn(
                        min_value=0,
                        max_value=10,
                        format="%.1f",
                    ),
                    "Tech": st.column_config.NumberColumn(format="%.0f", width="small"),
                    "Sent": st.column_config.NumberColumn(format="%.0f", width="small"),
                    "SmMny": st.column_config.NumberColumn(
                        format="%.0f", width="small"
                    ),
                    "Regime": st.column_config.NumberColumn(
                        format="%.0f", width="small"
                    ),
                    "R:R score": st.column_config.NumberColumn(
                        format="%.0f", width="small"
                    ),
                    "SL dist%": st.column_config.NumberColumn(format="%.2f%%"),
                    "T1 dist%": st.column_config.NumberColumn(format="%.2f%%"),
                    "R:R": st.column_config.NumberColumn(format="%.2f×"),
                },
            )

            st.subheader("Deep Dive")
            symbol = st.selectbox(
                "Pick a symbol",
                df["Symbol"].tolist() if not df.empty else [],
            )
            if symbol:
                _render_stock_chart(symbol)
                if st.button(f"🔄 Run /analyze for {symbol}", key=f"sig_an_{symbol}"):
                    _render_analyze_result(symbol, "NSE")
with tabs[2]:
    st.title("💼 Mock Portfolios")

    with SessionLocal() as db:
        portfolios = db.query(MockPortfolio).all()

    # ── Create new portfolio ─────────────────────────────────────────────
    with st.expander("+ Create New Portfolio", expanded=not portfolios):
        np_col1, np_col2, np_col3 = st.columns([2, 2, 1])
        new_name = np_col1.text_input(
            "Portfolio Name", placeholder="e.g. swing_2026", key="new_port_name"
        )
        new_capital = np_col2.number_input(
            "Initial Capital (₹)",
            min_value=10000,
            max_value=10_000_000,
            value=100000,
            step=10000,
            key="new_port_capital",
        )
        if np_col3.button("Create", type="primary", key="new_port_btn"):
            if new_name.strip():
                from plutus.backtesting.paper_trader import PaperTrader

                try:
                    PaperTrader.create_portfolio(new_name.strip(), float(new_capital))
                    st.success(
                        f"Portfolio '{new_name.strip()}' created with ₹{new_capital:,.0f}"
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed: {exc}")
            else:
                st.warning("Enter a portfolio name.")

    if not portfolios:
        st.info("No portfolios yet. Create one above.")
        st.stop()

    names = [p.name for p in portfolios]
    selected = st.selectbox("Portfolio", names, key="port_select")
    summary = _get_portfolio_data(selected)

    # ── Top-level metrics ────────────────────────────────────────────────
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    total_pnl = summary["realised_pnl"] + summary["unrealised_pnl"]
    pnl_delta = f"₹{summary['unrealised_pnl']:+,.0f} unrealised"
    m1.metric("Initial Capital", f"₹{summary['initial_capital']:,.0f}")
    m2.metric("Current Value", f"₹{summary['current_value']:,.0f}")
    m3.metric("Realised P&L", f"₹{summary['realised_pnl']:+,.0f}")
    m4.metric("Unrealised P&L", f"₹{summary['unrealised_pnl']:+,.0f}")
    m5.metric("Win Rate", f"{summary['win_rate']:.0f}%")
    m6.metric("Open / Closed", f"{summary['open_count']} / {summary['closed_count']}")

    # ── Expectancy stats ────────────────────────────────────────────────
    hist = _get_trade_history(selected)
    if hist:
        df_hist = pd.DataFrame(hist)
        winners = df_hist[df_hist["realised_pnl"] > 0]["realised_pnl_pct"]
        losers = df_hist[df_hist["realised_pnl"] <= 0]["realised_pnl_pct"]
        avg_win = winners.mean() if len(winners) else 0.0
        avg_loss = losers.mean() if len(losers) else 0.0
        win_rate_dec = summary["win_rate"] / 100
        expectancy = (win_rate_dec * avg_win) + ((1 - win_rate_dec) * avg_loss)
        ea, eb, ec = st.columns(3)
        ea.metric("Avg Winner", f"{avg_win:.2f}%")
        eb.metric("Avg Loser", f"{avg_loss:.2f}%")
        ec.metric("Expectancy", f"{expectancy:.2f}%")

    st.divider()

    # ── Open Positions ───────────────────────────────────────────────────
    st.subheader("Open Positions")
    from plutus.backtesting.paper_trader import PaperTrader

    trader = PaperTrader(selected)
    positions = trader.get_positions()
    if positions:
        pos_df = pd.DataFrame(positions)
        pos_df["entry_date"] = pd.to_datetime(pos_df["entry_date"])
        pos_df["days_held"] = (pd.Timestamp.now() - pos_df["entry_date"]).dt.days
        display_cols = [
            "symbol",
            "shares",
            "entry_price",
            "current_price",
            "unrealised_pnl",
            "unrealised_pnl_pct",
            "capital_used",
            "days_held",
            "strategy_used",
        ]
        pos_df = pos_df[[c for c in display_cols if c in pos_df.columns]]
        st.dataframe(
            pos_df.rename(
                columns={
                    "symbol": "Symbol",
                    "shares": "Shares",
                    "entry_price": "Entry ₹",
                    "current_price": "LTP ₹",
                    "unrealised_pnl": "Unreal. P&L ₹",
                    "unrealised_pnl_pct": "Unreal. %",
                    "capital_used": "Capital ₹",
                    "days_held": "Days Held",
                    "strategy_used": "Strategy",
                }
            ),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Unreal. %": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )
    else:
        st.caption("No open positions.")

    # ── Equity Curve (selected portfolio + overlay) ─────────────────────
    st.subheader("Equity Curve")
    ec_tabs = st.tabs(["This Portfolio", "All Portfolios Overlay"])

    with ec_tabs[0]:
        if hist:
            df_ec = pd.DataFrame(hist).sort_values("exit_date")
            df_ec["cum_pnl"] = df_ec["realised_pnl"].cumsum()
            fig_ec = go.Figure()
            fig_ec.add_trace(
                go.Scatter(
                    x=df_ec["exit_date"],
                    y=df_ec["cum_pnl"],
                    mode="lines+markers",
                    fill="tozeroy",
                    fillcolor="rgba(22,163,74,0.1)",
                    line=dict(color="#16a34a"),
                    name="Cumulative P&L",
                )
            )
            fig_ec.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_ec.update_layout(
                height=350, yaxis_title="Cumulative P&L (₹)", showlegend=False
            )
            st.plotly_chart(fig_ec, use_container_width=True)
        else:
            st.caption("No closed trades yet.")

    with ec_tabs[1]:
        fig_ov = go.Figure()
        for p in portfolios:
            h = _get_trade_history(p.name)
            if not h:
                continue
            d = pd.DataFrame(h).sort_values("exit_date")
            d["cum_pnl"] = d["realised_pnl"].cumsum()
            fig_ov.add_trace(
                go.Scatter(
                    x=d["exit_date"],
                    y=d["cum_pnl"],
                    mode="lines+markers",
                    name=p.name,
                )
            )
        fig_ov.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_ov.update_layout(height=350, yaxis_title="Cumulative P&L (₹)")
        st.plotly_chart(fig_ov, use_container_width=True)

    # ── Trade History ────────────────────────────────────────────────────
    st.subheader("Trade History")
    if hist:
        d = pd.DataFrame(hist)
        sym_filter = st.text_input(
            "Filter by symbol (substring)", "", key="port_sym_filter"
        )
        if sym_filter:
            d = d[d["symbol"].str.contains(sym_filter.upper())]
        d["pnl_color"] = d["realised_pnl"].apply(lambda x: "🟢" if x > 0 else "🔴")
        d_display = d[
            [
                "symbol",
                "side",
                "entry_price",
                "entry_date",
                "exit_price",
                "exit_date",
                "shares",
                "realised_pnl",
                "realised_pnl_pct",
                "exit_reason",
            ]
        ].copy()
        d_display.columns = [
            "Symbol",
            "Side",
            "Entry ₹",
            "Entry Date",
            "Exit ₹",
            "Exit Date",
            "Shares",
            "P&L ₹",
            "P&L %",
            "Exit Reason",
        ]
        st.dataframe(
            d_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "P&L %": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )
    else:
        st.caption("No closed trades.")

    # ── Trade Entry ──────────────────────────────────────────────────────
    st.subheader("New Trade")
    c5, c6, c7, c8, c9 = st.columns([2, 1, 1, 1, 1])
    sym = c5.text_input("Symbol", "RELIANCE", key="ptc_sym")
    side = c6.selectbox("Side", ["BUY", "SELL"], key="ptc_side")
    shares_inp = c7.number_input("Shares", min_value=1, value=10, step=1, key="ptc_qty")
    price = c8.number_input(
        "Price (₹)", min_value=0.01, value=100.0, step=0.5, key="ptc_price"
    )
    if c9.button("Execute", type="primary"):
        try:
            if side == "BUY":
                result = trader.buy(sym.upper(), float(price), int(shares_inp))
                msg = f"✅ Bought {shares_inp} × {sym.upper()} @ ₹{price:.2f} (trade #{result.trade_id})"
                if result.warnings:
                    st.warning("\n".join(result.warnings))
                st.success(msg)
            else:
                result = trader.sell(sym.upper(), float(price), int(shares_inp))
                pnl = result["realised_pnl"]
                st.success(
                    f"✅ Sold {result['shares_closed']} × {sym.upper()} @ ₹{price:.2f} | P&L: ₹{pnl:+,.2f}"
                )
            st.rerun()
        except ValueError as e:
            st.error(f"⚠️ {e}")

    # ── Admin: Reset portfolio ───────────────────────────────────────────
    st.divider()
    with st.expander("⚠️ Danger Zone", expanded=False):
        st.warning(
            "Resetting a portfolio deletes ALL trades and resets cash to initial capital."
        )
        confirm_reset = st.checkbox(
            "I understand — reset all trades for this portfolio", key="reset_confirm"
        )
        if st.button(
            "Reset Portfolio",
            type="secondary",
            disabled=not confirm_reset,
            key="reset_btn",
        ):
            with SessionLocal() as db:
                port_obj = (
                    db.query(MockPortfolio)
                    .filter(MockPortfolio.name == selected)
                    .first()
                )
                if port_obj:
                    db.query(PaperTrade).filter(
                        PaperTrade.portfolio_id == port_obj.id
                    ).delete()
                    db.commit()
            st.success(f"Portfolio '{selected}' has been reset.")
            st.rerun()

    # ── Alert history ────────────────────────────────────────────────────
    st.divider()
    st.subheader("Alert History (last 7 days)")
    try:
        from plutus.db.models import Alert as AlertModel
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=7)
        with SessionLocal() as db:
            port_obj = (
                db.query(MockPortfolio).filter(MockPortfolio.name == selected).first()
            )
            if port_obj:
                recent_alerts = (
                    db.query(AlertModel)
                    .filter(
                        AlertModel.portfolio_id == port_obj.id,
                        AlertModel.triggered_at >= cutoff,
                    )
                    .order_by(AlertModel.triggered_at.desc())
                    .limit(50)
                    .all()
                )
                if recent_alerts:
                    st.caption(f"{len(recent_alerts)} alerts in the last 7 days")
                    for a in recent_alerts:
                        icon = {
                            "PRE_SL_WARNING": "⚠️",
                            "TARGET1_HIT": "🎯",
                            "TARGET2_HIT": "🎯🎯",
                            "TREND_INVALIDATED": "📉",
                        }.get(a.alert_type.value if a.alert_type else "", "🔔")
                        ts = (
                            a.triggered_at.strftime("%d %b %H:%M")
                            if a.triggered_at
                            else "?"
                        )
                        st.caption(
                            f"{icon} `{ts}` **{a.symbol}** — {a.alert_type.value} @ ₹{a.ltp_at_trigger or '?'}"
                        )
                else:
                    st.caption("No alerts in the last 7 days.")
    except Exception:
        st.caption("Alert history unavailable.")

with tabs[3]:
    st.title("🧪 Strategy Lab")

    BUNDLES = ["trend", "reversal", "breakout", "smc", "composite"]

    with SessionLocal() as db:
        # Latest backtest snapshot — one row per bundle.
        latest = (
            db.query(BacktestResult)
            .order_by(BacktestResult.run_date.desc())
            .limit(50)
            .all()
        )

    if latest:
        # Keep one (latest) row per bundle name
        seen, dedup = set(), []
        for r in latest:
            if r.bundle_name in seen:
                continue
            seen.add(r.bundle_name)
            dedup.append(r)

        df = pd.DataFrame(
            [
                {
                    "Bundle": r.bundle_name,
                    "Win Rate": f"{r.win_rate:.1%}",
                    "Avg Return": f"{r.avg_return_pct:.2f}%",
                    "Max DD": f"{r.max_drawdown_pct:.2f}%",
                    "Sharpe": round(r.sharpe_ratio, 3),
                    "Trades": r.total_trades,
                    "Weight": (
                        f"{r.weight_assigned:.1%}"
                        if r.weight_assigned is not None
                        else "—"
                    ),
                }
                for r in dedup
                if r.bundle_name in BUNDLES
            ]
        )
        st.subheader("5-Bundle Comparison")
        st.dataframe(df, use_container_width=True, hide_index=True)

        fig = px.bar(
            df,
            x="Bundle",
            y="Sharpe",
            color="Sharpe",
            color_continuous_scale="RdYlGn",
            title="Sharpe by Bundle",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Equity-curve overlay (loaded from JSON column on BacktestResult)
        st.subheader("Equity Curve Overlay")
        fig2 = go.Figure()
        for r in dedup:
            if not r.equity_curve_json:
                continue
            curve = pd.read_json(r.equity_curve_json)
            fig2.add_trace(
                go.Scatter(
                    x=curve["date"],
                    y=curve["equity"],
                    mode="lines",
                    name=r.bundle_name,
                )
            )
        fig2.update_layout(height=380, yaxis_title="Equity (₹)")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Manual Backtest")
    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    sym = c1.text_input("Symbol", "RELIANCE", key="bt_sym")
    days = c2.number_input(
        "Days", value=365, min_value=30, max_value=730, key="bt_days"
    )
    bundle = c3.selectbox("Bundle", BUNDLES + ["all 5"], key="bt_bundle")
    if c4.button("Run", key="bt_run"):
        from plutus.backtesting.runner import run_bundle, run_all_bundles

        with st.spinner(f"Backtesting {sym} ({days} days)…"):
            try:
                if bundle == "all 5":
                    results = run_all_bundles(sym, days=days)
                    for name, r in results.items():
                        st.metric(f"{name} — Sharpe", f"{r.sharpe_ratio:.3f}")
                else:
                    r = run_bundle(sym, bundle, days=days)
                    st.success(
                        f"Win Rate {r.win_rate:.1%} | Sharpe {r.sharpe_ratio:.3f} | "
                        f"Trades {r.total_trades}"
                    )
            except Exception as e:
                st.error(f"Backtest failed: {str(e)[:200]}")
                st.info(
                    "This may be due to yfinance rate limits. Try again in a few minutes or during market hours."
                )
with tabs[4]:
    st.title("📰 News Feed")

    cutoff = datetime.utcnow() - timedelta(days=7)

    # ---- 5a. Material events (last 7d) ----
    st.subheader("🚨 Material Events (last 7d)")
    with SessionLocal() as db:
        material = (
            db.query(NewsEvent)
            .filter(NewsEvent.is_material.is_(True))
            .filter(NewsEvent.published_at >= cutoff)
            .order_by(NewsEvent.published_at.desc())
            .limit(100)
            .all()
        )
    if not material:
        st.caption("No material events fired in the last 7 days.")
    else:
        mat_df = pd.DataFrame(
            [
                {
                    "Time": n.published_at.strftime("%Y-%m-%d %H:%M"),
                    "Symbol": n.symbol,
                    "Event Type": n.material_event_type or "",
                    "Sentiment": n.sentiment_label or "",
                    "Headline": n.headline,
                    "Source": n.source,
                }
                for n in material
            ]
        )
        st.dataframe(mat_df, use_container_width=True, hide_index=True)

    st.divider()

    # ---- 5b. Rejected headlines (last 7d) ----
    st.subheader("🗑 Rejected Headlines (last 7d)")
    sym_q = st.text_input("Search by symbol", "", key="rej_search").upper().strip()
    with SessionLocal() as db:
        q = db.query(RejectedHeadline).filter(RejectedHeadline.rejected_at >= cutoff)
        if sym_q:
            q = q.filter(RejectedHeadline.symbol == sym_q)
        rejected = q.order_by(RejectedHeadline.rejected_at.desc()).limit(200).all()

    if not rejected:
        st.caption("No rejected headlines match.")
    else:
        for h in rejected:
            cols = st.columns([2, 1.5, 5, 1.5, 1.5, 1.5])
            cols[0].text(h.rejected_at.strftime("%Y-%m-%d %H:%M"))
            cols[1].text(h.symbol or "—")
            cols[2].markdown(f"**{h.headline}**")
            cols[3].text(h.source or "—")
            cols[4].text(h.filter_status)
            if cols[5].button("Promote keyword", key=f"prom_{h.id}"):
                suggested = _suggest_keyword(h.headline)
                st.code(
                    "Add to material_keywords.yaml under tier_A:\n"
                    f"  - {suggested}\n"
                    "Then restart plutus-main.service.",
                    language="yaml",
                )
with tabs[5]:
    st.title("👁 Watchlist")

    with SessionLocal() as db:
        items = db.query(Watchlist).order_by(Watchlist.symbol.asc()).all()

    # Add / remove form
    c1, c2, c3 = st.columns([2, 1, 1])
    new_sym = c1.text_input("Add symbol (NSE)", "", key="wl_new").upper().strip()
    exch = c2.selectbox("Exchange", ["NSE", "BSE"], key="wl_exch")
    if c3.button("Add to watchlist") and new_sym:
        with SessionLocal() as db:
            if not db.query(Watchlist).filter_by(symbol=new_sym).first():
                db.add(Watchlist(symbol=new_sym, exchange=exch))
                db.commit()
                st.success(f"Added {new_sym}.")
                st.rerun()

    if not items:
        st.info(
            "Watchlist empty. Add stocks above or via Telegram: `/watch add RELIANCE`."
        )
    else:
        for item in items:
            with st.expander(f"📌 {item.symbol} ({item.exchange or 'NSE'})"):
                cc1, cc2 = st.columns([3, 1])
                with cc1:
                    try:
                        price = fetch_live_price(item.symbol)
                        st.metric("LTP", f"₹{price:,.2f}")
                    except Exception:
                        st.caption("Live price unavailable.")
                    _render_stock_chart(item.symbol, days=60)
                with cc2:
                    if st.button(
                        f"🔄 Run /analyze for {item.symbol}",
                        key=f"wl_an_{item.id}",
                    ):
                        _render_analyze_result(item.symbol, item.exchange or "NSE")
                    if st.button("Remove", key=f"wl_rm_{item.id}"):
                        with SessionLocal() as db:
                            db.query(Watchlist).filter_by(id=item.id).delete()
                            db.commit()
                        st.rerun()
with tabs[6]:
    st.title("📋 Weekly Analysis History")

    with SessionLocal() as db:
        runs = db.query(WeeklyRun).order_by(WeeklyRun.id.desc()).all()
    if not runs:
        st.info("No history yet.")
    else:
        # Quarter / month filter
        all_quarters = sorted({_quarter_key(r.run_date) for r in runs}, reverse=True)
        all_months = sorted({r.run_date.strftime("%Y-%m") for r in runs}, reverse=True)
        c1, c2 = st.columns(2)
        q_pick = c1.selectbox("Filter by quarter", ["All"] + all_quarters)
        m_pick = c2.selectbox("Filter by month", ["All"] + all_months)
        filtered = []
        for r in runs:
            if q_pick != "All" and _quarter_key(r.run_date) != q_pick:
                continue
            if m_pick != "All" and r.run_date.strftime("%Y-%m") != m_pick:
                continue
            filtered.append(r)

        # Top-level table with win-rate-so-far per run
        rows: List[Dict[str, Any]] = []
        for r in filtered:
            stats = _outcome_stats_for_run(r.id)
            wr_so_far = (
                (stats["HIT_T1"] + stats["HIT_T2"]) / max(1, stats["closed"]) * 100
                if stats["closed"]
                else 0.0
            )
            rows.append(
                {
                    "Run Date": str(r.run_date),
                    "Market": r.market_regime or "N/A",
                    "BUY": r.total_buy_signals,
                    "WATCH": r.total_watch_signals,
                    "Closed": stats["closed"],
                    "Win % so far": round(wr_so_far, 1),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Drill-down per run
        run_choice = st.selectbox("Open run", [str(r.run_date) for r in filtered])
        if run_choice:
            chosen = next(r for r in filtered if str(r.run_date) == run_choice)
            _render_history_drilldown(chosen)
with tabs[7]:
    st.title("⚙️ Settings")

    # ── Trading Parameters (editable) ────────────────────────────────────────
    st.subheader("Trading Parameters")
    try:
        from plutus.config_params import get_param_meta, set_param, params_version_id

        param_meta = get_param_meta()

        cols = st.columns(2)
        inputs: dict = {}

        def _num_input(key: str, col):
            meta = param_meta.get(key, {})
            label = meta.get("label", key)
            current = meta.get("value", 0)
            min_v = float(meta.get("min") or 0)
            max_v = float(meta.get("max") or 1e9)
            vtype = meta.get("value_type", "float")
            if vtype == "int":
                return col.number_input(
                    label,
                    value=int(current),
                    min_value=int(min_v),
                    max_value=int(max_v),
                    step=1,
                    key=f"tp_{key}",
                )
            return col.number_input(
                label,
                value=float(current),
                min_value=min_v,
                max_value=max_v,
                step=0.5,
                format="%.1f",
                key=f"tp_{key}",
            )

        inputs["initial_capital"] = _num_input("initial_capital", cols[0])
        inputs["max_risk_pct_per_trade"] = _num_input("max_risk_pct_per_trade", cols[1])
        inputs["min_rr_ratio"] = _num_input("min_rr_ratio", cols[0])
        inputs["max_open_positions"] = _num_input("max_open_positions", cols[1])
        inputs["hold_days_min"] = _num_input("hold_days_min", cols[0])
        inputs["hold_days_max"] = _num_input("hold_days_max", cols[1])
        inputs["max_pct_capital_per_trade"] = _num_input(
            "max_pct_capital_per_trade", cols[0]
        )

        st.divider()
        st.caption("Score thresholds (must satisfy: buy > watch > avoid)")
        inputs["buy_threshold"] = _num_input("buy_threshold", cols[0])
        inputs["watch_threshold"] = _num_input("watch_threshold", cols[1])
        inputs["avoid_threshold"] = _num_input("avoid_threshold", cols[0])

        save_btn = st.button(
            "💾 Save Parameters", type="primary", key="save_params_btn"
        )

        if save_btn:
            errors = []
            if inputs["buy_threshold"] <= inputs["watch_threshold"]:
                errors.append("BUY threshold must be > WATCH threshold")
            if inputs["watch_threshold"] <= inputs["avoid_threshold"]:
                errors.append("WATCH threshold must be > AVOID threshold")
            if inputs["hold_days_min"] > inputs["hold_days_max"]:
                errors.append("Hold days min must be ≤ max")
            if errors:
                for e in errors:
                    st.error(e)
            else:
                try:
                    for key, val in inputs.items():
                        set_param(key, val, updated_by="dashboard")
                    new_ver = params_version_id()
                    st.success(f"Parameters saved. Params version: `{new_ver}`")
                    st.info(
                        "Re-run the weekly pipeline to apply new parameters to recommendations."
                    )
                except Exception as exc:
                    st.error(f"Save failed: {exc}")

        # Show current params version
        ver = params_version_id()
        st.caption(f"Current params version: `{ver}`")

    except Exception as exc:
        st.warning(f"Could not load editable parameters: {exc}")
        st.subheader("Trading Parameters (read-only fallback)")
        st.json(
            {
                "initial_capital": settings.INITIAL_CAPITAL,
                "max_risk_pct": settings.MAX_RISK_PCT,
                "min_rr_ratio": settings.MIN_RR_RATIO,
            }
        )

    # ── Tuning Suggestions ───────────────────────────────────────────────────
    st.divider()
    st.subheader("🔧 Tuning Suggestions")
    try:
        with SessionLocal() as db:
            from plutus.db.models import TuningSuggestion

            suggestions = (
                db.query(TuningSuggestion)
                .filter(TuningSuggestion.status == "pending")
                .order_by(TuningSuggestion.report_date.desc())
                .limit(20)
                .all()
            )
        if not suggestions:
            st.caption("No pending tuning suggestions.")
        else:
            for s in suggestions:
                with st.expander(
                    f"[{s.dimension}] {s.dimension_value} — {s.current_win_rate:.0%} win rate (n={s.n_trades})"
                ):
                    st.write(s.suggestion_text)
                    c1, c2, c3 = st.columns(3)
                    if c1.button("✅ Apply", key=f"sug_apply_{s.id}"):
                        from plutus.weekly.tuner import apply_suggestion

                        with SessionLocal() as db2:
                            ok = apply_suggestion(s.id, db_session=db2)
                        st.success("Applied." if ok else "Already applied.")
                        st.rerun()
                    if c2.button("❌ Reject", key=f"sug_reject_{s.id}"):
                        with SessionLocal() as db2:
                            row = db2.query(TuningSuggestion).get(s.id)
                            if row:
                                row.status = "rejected"
                                db2.commit()
                        st.rerun()
                    if c3.button("⏸ Defer", key=f"sug_defer_{s.id}"):
                        with SessionLocal() as db2:
                            row = db2.query(TuningSuggestion).get(s.id)
                            if row:
                                row.status = "deferred"
                                db2.commit()
                        st.rerun()
    except Exception as exc:
        st.caption(f"Could not load suggestions: {exc}")

    # ── Material-keyword Filter ──────────────────────────────────────────────
    st.divider()
    st.subheader("Material-keyword Filter")
    st.write(f"**Enabled tiers:** `{settings.MATERIAL_KEYWORD_TIERS}`")
    st.caption(
        "Edit `src/plutus/data/material_keywords.yaml` and restart "
        "`plutus-main.service` to apply changes."
    )

    st.subheader("Services")
    services = _service_status()
    sdf = pd.DataFrame([{"Service": k, "Status": v} for k, v in services.items()])
    st.dataframe(sdf, use_container_width=True, hide_index=True)

    st.subheader("Last Weekly Run")
    with SessionLocal() as db:
        last = db.query(WeeklyRun).order_by(WeeklyRun.id.desc()).first()
    if last:
        st.write(
            f"Run date **{last.run_date}** — completed at "
            f"{last.completed_at.strftime('%Y-%m-%d %H:%M:%S') if last.completed_at else 'N/A'}"
        )
    else:
        st.caption("No weekly run recorded yet.")

    st.subheader("API Endpoint")
    st.code(
        f"POST {API_BASE}/analyze\n"
        "Header: X-API-Key: ***\n"
        'Body:   {"symbol": "RELIANCE", "exchange": "NSE"}\n'
        "Notes:  30 calls/hour per key, 5-minute symbol cache (cache_hit in response)."
    )
