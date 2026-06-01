# 11 — Streamlit Dashboard

> Single file: `src/dashboard.py`. **8 tabs (Settings is a tab, not a sidebar).**
> Reads from PostgreSQL; calls `/analyze` over HTTP so all on-demand analysis goes through
> the cache + rate limiter (see `09_api.md` and CHANGE_SPEC §6).
>
> Run:
>
> ```bash
> streamlit run src/dashboard.py --server.port 8501 --server.address 0.0.0.0
> ```

---

## Top of File — Imports & Tab Structure

```python
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

API_BASE = f"http://127.0.0.1:{settings.API_PORT}"   # default http://127.0.0.1:8000 — /analyze goes through cache + rate limit
API_KEY = settings.API_KEY                            # local API key for self-calls

st.set_page_config(
    page_title="Plutus — Indian Equities Recommendation Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

tabs = st.tabs([
    "🏠 Home",
    "📊 Signals",
    "💼 Portfolio",
    "🧪 Strategy Lab",
    "📰 News Feed",
    "👁 Watchlist",
    "📋 History",
    "⚙️ Settings",
])
```

---

## Tab 1: 🏠 Home

Weekly summary card + top picks at a glance. Includes a `Run /analyze` button on each pick
so the user can refresh the analysis through the cached API endpoint.

```python
with tabs[0]:
    st.title("📈 Plutus — Weekly Picks")
    st.caption(f"Loaded: {datetime.now().strftime('%d %b %Y %H:%M')} IST")

    with SessionLocal() as db:
        latest_run = (
            db.query(WeeklyRun).order_by(WeeklyRun.run_date.desc()).first()
        )
        if not latest_run:
            st.info("No weekly analysis yet. Next run: Sunday 18:00 IST.")
        else:
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
                    if st.button(f"🔄 Run /analyze for {rec.symbol}", key=f"home_an_{rec.id}"):
                        _render_analyze_result(rec.symbol, rec.exchange or "NSE")
```

---

## Tab 2: 📊 Signals

Full sortable recommendation table with Monday `revalidation_note` column when populated.

```python
with tabs[1]:
    st.title("📊 Signal Board")

    with SessionLocal() as db:
        latest_run = (
            db.query(WeeklyRun).order_by(WeeklyRun.run_date.desc()).first()
        )
        if not latest_run:
            st.info("No data yet.")
        else:
            recs = (
                db.query(Recommendation)
                .filter(Recommendation.weekly_run_id == latest_run.id)
                .order_by(Recommendation.confidence.desc())
                .all()
            )

            rows: List[Dict[str, Any]] = []
            for r in recs:
                rows.append({
                    "Symbol": r.symbol,
                    "Signal": r.recommendation.value,
                    "Score": r.confidence,
                    "Entry Low": r.entry_low,
                    "Entry Mid": r.entry_mid,
                    "Entry High": r.entry_high,
                    "Target 1": r.target1,
                    "Target 2": r.target2,
                    "Stop Loss": r.stop_loss,
                    "R:R": r.rr_ratio,
                    "Hold (min)": r.hold_days_min,
                    "Hold (max)": r.hold_days_max,
                    "Strategy": r.strategy_used,
                    "Revalidation": r.revalidation_note or "",
                    "Outcome": r.outcome.value if r.outcome else "PENDING",
                })
            df = pd.DataFrame(rows)

            signal_filter = st.multiselect(
                "Filter by signal",
                ["BUY", "WATCH", "HOLD", "AVOID"],
                default=["BUY", "WATCH"],
            )
            if signal_filter:
                df = df[df["Signal"].isin(signal_filter)]

            # Hide the Revalidation column entirely if no row has one.
            if not df["Revalidation"].any():
                df = df.drop(columns=["Revalidation"])

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Score": st.column_config.ProgressColumn(min_value=0, max_value=10),
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
```

---

## Tab 3: 💼 Portfolio

Multi-portfolio dropdown, equity curve, per-portfolio summary card, trade history with
filter, and a `/buy /sell` pre-trade check button (mirrors the bot's risk-line warning).

```python
with tabs[2]:
    st.title("💼 Mock Portfolios")

    with SessionLocal() as db:
        portfolios = db.query(MockPortfolio).all()

    if not portfolios:
        st.info("No portfolios yet. Create one via Telegram: `/portfolio new myport 100000`.")
    else:
        names = [p.name for p in portfolios]
        selected = st.selectbox("Portfolio", names)
        summary = _get_portfolio_data(selected)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Initial Capital", f"₹{summary['initial_capital']:,.0f}")
        c2.metric(
            "Realised P&L",
            f"₹{summary['realised_pnl']:,.0f}",
            delta=f"{summary['realised_pnl_pct']:.2f}%",
        )
        c3.metric("Win Rate", f"{summary['win_rate']:.0f}%")
        c4.metric("Open Positions", summary["open_positions"])

        # Equity-curve overlay across all portfolios
        st.subheader("Equity Curve Overlay")
        fig = go.Figure()
        for p in portfolios:
            hist = _get_trade_history(p.name)
            if not hist:
                continue
            d = pd.DataFrame(hist).sort_values("exit_date")
            d["cum_pnl"] = d["realised_pnl"].cumsum()
            fig.add_trace(go.Scatter(
                x=d["exit_date"], y=d["cum_pnl"], mode="lines+markers", name=p.name,
            ))
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.update_layout(height=380, yaxis_title="Cumulative P&L (₹)")
        st.plotly_chart(fig, use_container_width=True)

        # Trade history table with filter
        st.subheader("Trade History")
        hist = _get_trade_history(selected)
        if hist:
            d = pd.DataFrame(hist)
            sym_filter = st.text_input("Filter by symbol (substring)", "")
            if sym_filter:
                d = d[d["symbol"].str.contains(sym_filter.upper())]
            st.dataframe(d, use_container_width=True, hide_index=True)

        # /buy /sell pre-trade check button
        st.subheader("Pre-trade Check")
        c5, c6, c7, c8 = st.columns([2, 1, 1, 1])
        sym = c5.text_input("Symbol", "RELIANCE", key="ptc_sym")
        side = c6.selectbox("Side", ["BUY", "SELL"], key="ptc_side")
        shares = c7.number_input("Shares", min_value=1, value=10, step=1, key="ptc_qty")
        if c8.button("Check"):
            check = _pretrade_check(selected, sym, side, int(shares))
            st.code(check, language="text")
```

---

## Tab 4: 🧪 Strategy Lab

5-bundle comparison table (Trend, Reversal, Breakout, SMC, Composite), equity-curve overlay,
and a manual backtest form that accepts symbol + date range + bundle name (or "all 5").

```python
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

        df = pd.DataFrame([{
            "Bundle": r.bundle_name,
            "Win Rate": f"{r.win_rate:.1%}",
            "Avg Return": f"{r.avg_return_pct:.2f}%",
            "Max DD": f"{r.max_drawdown_pct:.2f}%",
            "Sharpe": round(r.sharpe_ratio, 3),
            "Trades": r.total_trades,
            "Weight": f"{r.weight_assigned:.1%}",
        } for r in dedup if r.bundle_name in BUNDLES])
        st.subheader("5-Bundle Comparison")
        st.dataframe(df, use_container_width=True, hide_index=True)

        fig = px.bar(
            df, x="Bundle", y="Sharpe",
            color="Sharpe", color_continuous_scale="RdYlGn",
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
            fig2.add_trace(go.Scatter(
                x=curve["date"], y=curve["equity"],
                mode="lines", name=r.bundle_name,
            ))
        fig2.update_layout(height=380, yaxis_title="Equity (₹)")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Manual Backtest")
    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    sym = c1.text_input("Symbol", "RELIANCE", key="bt_sym")
    start = c2.date_input("Start", value=date.today() - timedelta(days=180), key="bt_start")
    end = c3.date_input("End", value=date.today(), key="bt_end")
    bundle = c4.selectbox("Bundle", BUNDLES + ["all 5"], key="bt_bundle")
    if st.button("Run backtest"):
        from plutus.backtesting.runner import run_bundle, run_all_bundles
        with st.spinner(f"Backtesting {sym}…"):
            if bundle == "all 5":
                results = run_all_bundles(sym, start=start, end=end)
                for name, r in results.items():
                    st.metric(f"{name} — Sharpe", f"{r.sharpe_ratio:.3f}")
            else:
                r = run_bundle(sym, bundle, start=start, end=end)
                st.success(
                    f"Win Rate {r.win_rate:.1%} | Sharpe {r.sharpe_ratio:.3f} | "
                    f"Trades {r.total_trades}"
                )
```

---

## Tab 5: 📰 News Feed

Two sub-sections per CHANGE_SPEC §5: Material Events and Rejected Headlines.

```python
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
        mat_df = pd.DataFrame([{
            "Time": n.published_at.strftime("%Y-%m-%d %H:%M"),
            "Symbol": n.symbol,
            "Event Type": n.material_event_type or "",
            "Sentiment": n.sentiment_label or "",
            "Headline": n.headline,
            "Source": n.source,
        } for n in material])
        st.dataframe(mat_df, use_container_width=True, hide_index=True)

    st.divider()

    # ---- 5b. Rejected headlines (last 7d) ----
    st.subheader("🗑 Rejected Headlines (last 7d)")
    sym_q = st.text_input("Search by symbol", "", key="rej_search").upper().strip()
    with SessionLocal() as db:
        q = (
            db.query(RejectedHeadline)
            .filter(RejectedHeadline.rejected_at >= cutoff)
        )
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
```

---

## Tab 6: 👁 Watchlist

Manage tracked stocks and run a per-stock mini-analysis through the cached API.

```python
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
        st.info("Watchlist empty. Add stocks above or via Telegram: `/watch add RELIANCE`.")
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
```

---

## Tab 7: 📋 History

Date-sortable table of `weekly_runs` with quarter/month filter. Click a row → expands the
markdown body, recommendations table, outcomes summary card, and equity curve. See
`14_weekly_history.md` for the outcome-tracker contract that feeds this view.

```python
with tabs[6]:
    st.title("📋 Weekly Analysis History")

    with SessionLocal() as db:
        runs = (
            db.query(WeeklyRun).order_by(WeeklyRun.run_date.desc()).all()
        )
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
                stats["HIT_T1"] + stats["HIT_T2"]
            ) / max(1, stats["closed"]) * 100 if stats["closed"] else 0.0
            rows.append({
                "Run Date": str(r.run_date),
                "Market": r.market_regime or "N/A",
                "BUY": r.total_buy_signals,
                "WATCH": r.total_watch_signals,
                "Closed": stats["closed"],
                "Win % so far": round(wr_so_far, 1),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Drill-down per run
        run_choice = st.selectbox(
            "Open run", [str(r.run_date) for r in filtered]
        )
        if run_choice:
            chosen = next(r for r in filtered if str(r.run_date) == run_choice)
            _render_history_drilldown(chosen)
```

---

## Tab 8: ⚙️ Settings

Display config (redacted), running services, last weekly run timestamp, current
`MATERIAL_KEYWORD_TIERS`.

```python
with tabs[7]:
    st.title("⚙️ Settings")

    st.subheader("Trading Parameters")
    st.json({
        "initial_capital": settings.INITIAL_CAPITAL,
        "max_risk_pct": settings.MAX_RISK_PCT,
        "min_rr_ratio": settings.MIN_RR_RATIO,
        "max_open_positions_advisory": settings.MAX_OPEN_POSITIONS_ADVISORY,
        "max_open_positions_hard": settings.MAX_OPEN_POSITIONS_HARD,
        "hold_days_default": f"{settings.HOLD_DAYS_MIN}–{settings.HOLD_DAYS_MAX}",
    })

    st.subheader("Environment (redacted)")
    st.json(_redacted_env_summary())

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
        last = db.query(WeeklyRun).order_by(WeeklyRun.run_date.desc()).first()
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
        "Body:   {\"symbol\": \"RELIANCE\", \"exchange\": \"NSE\"}\n"
        "Notes:  30 calls/hour per key, 5-minute symbol cache (cache_hit in response)."
    )
```

---

## Helper Functions (bottom of `src/dashboard.py`)

```python
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


def _get_trade_history(name: str) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        p = db.query(MockPortfolio).filter(MockPortfolio.name == name).first()
        if not p:
            return []
        trades = (
            db.query(PaperTrade)
            .filter(PaperTrade.portfolio_id == p.id, PaperTrade.status == TradeStatus.CLOSED)
            .order_by(PaperTrade.exit_date.asc())
            .all()
        )
    return [{
        "symbol": t.symbol,
        "side": t.direction.value,
        "entry_price": t.entry_price,
        "entry_date": t.entry_date,
        "exit_price": t.exit_price,
        "exit_date": t.exit_date,
        "shares": t.shares,
        "realised_pnl": t.realised_pnl,
        "realised_pnl_pct": t.realised_pnl_pct,
        "exit_reason": t.exit_reason.value if t.exit_reason else None,
    } for t in trades]


def _render_stock_chart(symbol: str, days: int = 60) -> None:
    """Candlestick + EMA21/EMA50."""
    try:
        df = add_indicators(fetch_ohlcv(symbol, days=days))
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"], name=symbol,
        ))
        fig.add_trace(go.Scatter(
            x=df.index, y=df["EMA_21"], name="EMA21",
            line=dict(color="blue", width=1),
        ))
        fig.add_trace(go.Scatter(
            x=df.index, y=df["EMA_50"], name="EMA50",
            line=dict(color="orange", width=1.5),
        ))
        fig.update_layout(
            title=f"{symbol} — {days}-day chart",
            xaxis_rangeslider_visible=False,
            height=420,
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Chart unavailable: {e}")


def _render_analyze_result(symbol: str, exchange: str = "NSE") -> None:
    """POST /analyze through the cached + rate-limited API."""
    try:
        with httpx.Client(timeout=30.0) as cli:
            resp = cli.post(
                f"{API_BASE}/analyze",
                headers={"X-API-Key": API_KEY},
                json={"symbol": symbol, "exchange": exchange},
            )
        if resp.status_code == 429:
            data = resp.json()
            st.warning(
                f"Rate limit hit. Retry in {data.get('retry_after_seconds', '?')}s."
            )
            return
        resp.raise_for_status()
        data = resp.json()
        cache_badge = "♻️ cache hit" if data.get("cache_hit") else "🆕 fresh"
        st.caption(f"Source: **{cache_badge}** · "
                   f"Rate limit remaining: {resp.headers.get('X-RateLimit-Remaining', '?')}")
        st.json(data)
    except Exception as e:
        st.error(f"/analyze failed: {e}")


def _pretrade_check(portfolio: str, symbol: str, side: str, shares: int) -> str:
    """Mirror of the Telegram bot's pre-trade risk-line warning."""
    from plutus.alerts.telegram_bot import format_pretrade_warning
    return format_pretrade_warning(portfolio, symbol, side, shares)


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
        rec_df = pd.DataFrame([{
            "Symbol": r.symbol,
            "Signal": r.recommendation.value,
            "Score": r.confidence,
            "Entry Mid": r.entry_mid,
            "T1": r.target1,
            "Stop": r.stop_loss,
            "Outcome": r.outcome.value if r.outcome else "PENDING",
            "P&L %": r.outcome_pct,
            "Exit Date": r.outcome_exit_date,
        } for r in recs])
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
        eq = pd.DataFrame({
            "exit_date": [r.outcome_exit_date for r in closed],
            "pnl_pct": [r.outcome_pct for r in closed],
        })
        eq["cum_pnl_pct"] = eq["pnl_pct"].cumsum()
        fig = px.line(
            eq, x="exit_date", y="cum_pnl_pct",
            title="Cumulative P&L % (closed recs from this run)",
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig, use_container_width=True)


def _redacted_env_summary() -> Dict[str, Any]:
    """Show env-derived settings, redacting anything that looks like a secret."""
    secret_keys = {
        "API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY",
        "TELEGRAM_BOT_TOKEN", "NEWS_API_KEY", "REDDIT_CLIENT_SECRET",
        "DB_PASSWORD",
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
                capture_output=True, text=True, timeout=2,
            )
            out[u] = (r.stdout or r.stderr).strip() or "unknown"
        except Exception:
            out[u] = "unknown"
    return out
```

---

## Cross-references

- `09_api.md` — `/analyze` contract, rate limit, 5-minute cache, `cache_hit` field.
- `10_telegram_bot.md` — `/buy` `/sell` `/confirm` flow used by the Pre-trade Check button.
- `12_scheduler.md` — Sunday weekly pipeline + Monday `weekly_revalidate` job that
  populates `revalidation_note`.
- `13_mock_portfolios.md` — `MockPortfolio` and `PaperTrade` schema used in Tab 3.
- `14_weekly_history.md` — outcome-tracker contract that feeds Tab 7 (History).
