from __future__ import annotations

import streamlit as st

from plutus.dashboard.api_client import fetch_portfolio_snapshot, trigger_price_check
from plutus.dashboard.components.cash_banner import cash_banner
from plutus.dashboard.components.regime_banner import regime_banner
from plutus.dashboard.components.tranche_pills import tranche_pills
from plutus.dashboard.data import HomeView
from plutus.dashboard.theme import (
    ACCUMULATION_ACCENT,
    BORDER,
    BUY_GREEN,
    BUY_GREEN_BG,
    CASH_ACCENT,
    DEAD_ZONE,
    DEAD_ZONE_BG,
    INFO_BLUE,
    INFO_BLUE_BG,
    LOSS_RED,
    REGIME_BEAR,
    SURFACE,
    SWING_ACCENT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)


def _inr(value: object) -> str:
    return f"₹{float(value):,.0f}"


_REGIME_PILL_STYLE = {
    "BULL": (BUY_GREEN, BUY_GREEN_BG),
    "BEAR": (LOSS_RED, "#2a1f1f"),
    "SIDEWAYS": (DEAD_ZONE, DEAD_ZONE_BG),
}


def _status_pill(label: str, kind: str = "paused") -> str:
    if kind.lower() == "active":
        fg, bg = INFO_BLUE, INFO_BLUE_BG
    else:
        fg, bg = DEAD_ZONE, DEAD_ZONE_BG
    return f'<span class="plutus-pill" style="background:{bg}; color:{fg};">{label}</span>'


def _swing_row(row) -> str:
    bar_pct = int(max(0.0, min(1.0, row.bar_pct)) * 100)
    return f"""
<div class="plutus-row">
  <span style="font-weight: 500;">{row.symbol}</span>
  <div class="plutus-bar-track">
    <div class="plutus-bar-fill" style="width:{bar_pct}%; background:{SWING_ACCENT};"></div>
  </div>
  <span style="text-align:right;">{row.score}</span>
  <span style="text-align:right; color:{DEAD_ZONE}; font-size: 10px;">{row.status}</span>
</div>
<div class="plutus-row-detail">{row.detail}</div>"""


def _accumulation_row(row) -> str:
    tranches = "".join(
        f'<span class="plutus-tranche" style="background:{ACCUMULATION_ACCENT}; color:#fff;">{s}</span>'
        if s in (row.tranches_filled or [])
        else f'<span class="plutus-tranche" style="background:{BORDER}; color:{TEXT_TERTIARY};">{s}</span>'
        for s in range(1, 4)
    )
    return f"""
<div style="display:grid; grid-template-columns: 100px 1fr 60px;
gap: 10px; align-items: center; font-size: 12px; padding: 6px 0;">
  <span style="font-weight: 500; color: {TEXT_PRIMARY};">{row.symbol}</span>
  <div>{tranches}</div>
  <span style="text-align:right; font-size: 11px; color: {TEXT_SECONDARY};">{row.score}</span>
</div>
<div class="plutus-row-detail" style="padding-left: 110px;">{row.detail}</div>"""


def _render_pnl_section() -> None:
    col_btn, col_check = st.columns([1, 1])
    with col_btn:
        if st.button("📊 Fetch live P/L", key="fetch_pnl"):
            st.session_state["pnl_snapshot"] = fetch_portfolio_snapshot()
    with col_check:
        if st.button("🔔 Run SL check now", key="run_sl_check"):
            result = trigger_price_check()
            if result:
                n = result.get("notifications_created", 0)
                if n > 0:
                    st.toast(f"Created {n} alert(s)")
                else:
                    st.toast("All positions within safe range")

    snapshot = st.session_state.get("pnl_snapshot")
    if snapshot is None:
        return

    total_pnl = snapshot["total_pnl"]
    total_pnl_pct = snapshot["total_pnl_pct"]
    pnl_color = BUY_GREEN if total_pnl >= 0 else LOSS_RED
    arrow = "▲" if total_pnl >= 0 else "▼"
    checked = snapshot["checked_at"][:16].replace("T", " ")

    st.markdown(
        f'<div class="plutus-card" style="margin:10px 0;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
        f'<span style="font-weight:500;color:{TEXT_PRIMARY};font-size:14px;">Live P/L</span>'
        f'<span style="font-size:10px;color:{TEXT_TERTIARY};">as of {checked} UTC</span>'
        f'</div>'
        f'<div style="display:flex;gap:24px;align-items:baseline;margin-bottom:10px;">'
        f'<span style="font-size:22px;font-weight:500;color:{pnl_color};">'
        f'{arrow} ₹{abs(total_pnl):,.2f}</span>'
        f'<span style="font-size:14px;color:{pnl_color};">{total_pnl_pct:+.2f}%</span>'
        f'<span style="font-size:11px;color:{TEXT_TERTIARY};">'
        f'Invested ₹{snapshot["total_invested"]:,.0f} · Current ₹{snapshot["total_current"]:,.0f}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    positions = snapshot.get("positions", [])
    if positions:
        header = (
            f'<div style="display:grid;grid-template-columns:90px 70px 80px 80px 80px 70px 1fr;'
            f'gap:8px;font-size:10px;color:{TEXT_TERTIARY};padding:4px 0;'
            f'border-bottom:0.5px solid {BORDER};text-transform:lowercase;letter-spacing:0.3px;">'
            f'<span>symbol</span><span>mode</span><span>avg cost</span>'
            f'<span>price</span><span>P/L</span><span>P/L %</span><span>SL dist</span></div>'
        )
        rows_html = header
        for p in sorted(positions, key=lambda x: x["pnl"], reverse=True):
            row_color = BUY_GREEN if p["pnl"] >= 0 else LOSS_RED
            sl_text = ""
            if p.get("sl_distance_pct") is not None:
                sl_val = p["sl_distance_pct"]
                sl_color = LOSS_RED if sl_val <= 3 else (SWING_ACCENT if sl_val <= 5 else TEXT_TERTIARY)
                sl_text = f'<span style="color:{sl_color};">{sl_val:.1f}%</span>'
            mode_color = SWING_ACCENT if p["mode"] == "swing" else ACCUMULATION_ACCENT
            rows_html += (
                f'<div style="display:grid;grid-template-columns:90px 70px 80px 80px 80px 70px 1fr;'
                f'gap:8px;font-size:12px;padding:4px 0;border-bottom:0.5px solid {BORDER}22;">'
                f'<span style="font-weight:500;color:{TEXT_PRIMARY};">{p["symbol"]}</span>'
                f'<span style="color:{mode_color};font-size:10px;">{p["mode"]}</span>'
                f'<span style="color:{TEXT_SECONDARY};">₹{p["avg_cost"]:,.0f}</span>'
                f'<span style="color:{TEXT_PRIMARY};">₹{p["current_price"]:,.0f}</span>'
                f'<span style="color:{row_color};">₹{p["pnl"]:+,.0f}</span>'
                f'<span style="color:{row_color};">{p["pnl_pct"]:+.1f}%</span>'
                f'<span>{sl_text}</span>'
                f'</div>'
            )
        rows_html += "</div>"
        st.markdown(rows_html, unsafe_allow_html=True)
    else:
        st.markdown("</div>", unsafe_allow_html=True)


def render(data: HomeView) -> None:
    """Home / Portfolio overview (spec 14 §4)."""
    if data is None:
        st.info("No data yet — trigger a pipeline run from User flow.")
        return
    regime = data.regime

    # Header
    pill_fg, pill_bg = _REGIME_PILL_STYLE.get(regime.label, (TEXT_SECONDARY, SURFACE))
    pct_above_ema = ""
    for r in (regime.reasons or []):
        if "above" in r.lower() or "below" in r.lower():
            pct_above_ema = r
            break
    st.markdown(
        f"""<div style="display:flex; align-items:center; justify-content: space-between;
margin-bottom: 14px;">
  <h1 style="margin:0;">Portfolio overview</h1>
  <div style="display:flex; align-items: center; gap: 10px;">
    <span class="plutus-pill" style="background:{pill_bg}; color:{pill_fg};">
      ● Nifty {regime.label} · {pct_above_ema or regime.confidence + ' confidence'}
    </span>
    <span style="font-size: 12px; color: {TEXT_SECONDARY};">{_inr(data.total_capital)}</span>
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # Metric cards
    cols = st.columns(4)
    cols[0].metric("Total capital", _inr(data.total_capital), "across both modes")
    cols[1].metric("Swing allocated", _inr(data.swing_allocated), "active trades")
    cols[2].metric("Accumulation allocated", _inr(data.accumulation_allocated), "tranches building")
    cols[3].metric("Cash reserve", _inr(data.cash_reserve), "deploy when BULL")

    # Allocation bar
    total = float(data.total_capital) or 1.0
    swing_pct = float(data.swing_allocated) / total * 100
    acc_pct = float(data.accumulation_allocated) / total * 100
    cash_pct = float(data.cash_reserve) / total * 100
    st.markdown(
        f"""<div style="margin: 12px 0 4px;">
  <div style="display:flex; height: 6px; border-radius: 3px; overflow: hidden;">
    <div style="width:{swing_pct}%; background:{SWING_ACCENT};"></div>
    <div style="width:{acc_pct}%; background:{ACCUMULATION_ACCENT};"></div>
    <div style="width:{cash_pct}%; background:{CASH_ACCENT};"></div>
  </div>
  <div style="display:flex; gap: 16px; font-size: 11px; color:{TEXT_TERTIARY}; margin-top: 6px;">
    <span><span style="display:inline-block; width:7px; height:7px; background:{SWING_ACCENT}; border-radius:50%; margin-right: 5px;"></span>Swing {swing_pct:.0f}%</span>
    <span><span style="display:inline-block; width:7px; height:7px; background:{ACCUMULATION_ACCENT}; border-radius:50%; margin-right: 5px;"></span>Accumulation {acc_pct:.0f}%</span>
    <span><span style="display:inline-block; width:7px; height:7px; background:{CASH_ACCENT}; border-radius:50%; margin-right: 5px;"></span>Cash {cash_pct:.0f}%</span>
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # Live P/L section
    _render_pnl_section()

    # Regime advisory + cash banner
    regime_banner(regime, data.cash_decision)
    if data.cash_decision is not None and data.cash_decision.deploy_count == 0:
        cash_banner(data.cash_decision)

    # Two-column panels
    left, right = st.columns(2)
    with left:
        swing_rows_html = "".join(_swing_row(r) for r in data.swing_rows[:5])
        st.markdown(
            f"""<div class="plutus-card">
<div style="display:flex; justify-content: space-between; margin-bottom: 8px;">
  <span style="font-weight: 500; color:{TEXT_PRIMARY};">⚡ Swing mode</span>
  {_status_pill(data.swing_mode, data.swing_mode)}
</div>
{swing_rows_html or '<div style="color:'+TEXT_TERTIARY+'; font-size: 12px;">No signals this run.</div>'}
<div style="margin-top: 8px; padding-top: 8px; border-top: 0.5px solid {BORDER};
font-size: 11px; color: {TEXT_SECONDARY};">View all signals →</div>
</div>""",
            unsafe_allow_html=True,
        )

    with right:
        acc_rows_html = "".join(_accumulation_row(r) for r in data.accumulation_rows[:5])
        st.markdown(
            f"""<div class="plutus-card">
<div style="display:flex; justify-content: space-between; margin-bottom: 8px;">
  <span style="font-weight: 500; color:{TEXT_PRIMARY};">📈 Accumulation mode</span>
  {_status_pill(data.accumulation_mode, data.accumulation_mode)}
</div>
{acc_rows_html or '<div style="color:'+TEXT_TERTIARY+'; font-size: 12px;">No candidates this run.</div>'}
<div style="margin-top: 8px; padding-top: 8px; border-top: 0.5px solid {BORDER};
font-size: 11px; color: {TEXT_SECONDARY};">View all candidates →</div>
</div>""",
            unsafe_allow_html=True,
        )
