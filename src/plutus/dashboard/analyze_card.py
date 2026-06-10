# src/plutus/dashboard/analyze_card.py
"""Structured recommendation card — pure Streamlit render, no DB or network."""
import streamlit as st
import httpx

REC_COLORS = {
    "BUY":   ("#16a34a", "✅"),
    "WATCH": ("#d97706", "👁"),
    "HOLD":  ("#2563eb", "⏸"),
    "SELL":  ("#dc2626", "⬇️"),
    "AVOID": ("#dc2626", "🚫"),
}


def render_analyze_card(data: dict) -> None:
    """Render a structured recommendation card from an /analyze API response."""
    rec = data.get("recommendation", "HOLD").upper()
    conf = data.get("confidence", 0.0)
    color, icon = REC_COLORS.get(rec, ("#6b7280", "❓"))

    # ── Badge + confidence ───────────────────────────────────────────────
    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
          <span style="background:{color};color:#fff;padding:6px 18px;border-radius:8px;
                font-size:1.3rem;font-weight:700">{icon} {rec}</span>
          <span style="font-size:1.1rem;color:{color};font-weight:600">
            Confidence: {conf:.1f}/10</span>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Key metrics ──────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Current Price", f"₹{data.get('current_price', 0):,.2f}")
    m2.metric("R:R", f"{data.get('risk_reward', 0):.2f}×")
    m3.metric("Hold Period", data.get("hold_days", "—"))
    m4.metric("Strategy", data.get("strategy", "—"))

    st.divider()

    # ── Price levels + position sizing ───────────────────────────────────
    left, right = st.columns(2)

    with left:
        st.subheader("Price Levels")
        ez = data.get("entry_zone", [0, 0])
        targets = data.get("targets", [])
        sl = data.get("stop_loss", 0)
        t1 = targets[0] if len(targets) > 0 else None
        t2 = targets[1] if len(targets) > 1 else None
        for label, value in [
            ("Entry Zone", f"₹{ez[0]:,.2f} – ₹{ez[1]:,.2f}"),
            ("Target 1 (T1)", f"₹{t1:,.2f}" if t1 else "—"),
            ("Target 2 (T2)", f"₹{t2:,.2f}" if t2 else "—"),
            ("Stop Loss", f"₹{sl:,.2f}"),
        ]:
            ca, cb = st.columns([1, 1])
            ca.write(f"**{label}**")
            cb.write(value)

    with right:
        st.subheader("Position Sizing")
        pos = data.get("position", {})
        for label, value in [
            ("Shares", str(pos.get("shares", 0))),
            ("Capital Deployed", f"₹{pos.get('capital', 0):,.2f}"),
            ("% of Portfolio", f"{pos.get('pct_of_portfolio', 0):.1f}%"),
            ("Max Loss (₹)", f"₹{pos.get('max_loss_inr', 0):,.2f}"),
        ]:
            ca, cb = st.columns([1, 1])
            ca.write(f"**{label}**")
            cb.write(value)

    # ── Risk flags ───────────────────────────────────────────────────────
    risk_flags = data.get("risk_flags", [])
    if risk_flags:
        st.divider()
        st.subheader("Risk Flags")
        for flag in risk_flags:
            st.warning(flag, icon="⚠️")

    # ── Signal details ───────────────────────────────────────────────────
    signals = data.get("signals", {})
    if signals:
        st.divider()
        with st.expander("Signal Details", expanded=False):
            s1, s2, s3 = st.columns(3)
            with s1:
                st.caption("**Technical**")
                for k, v in (signals.get("technical") or {}).items():
                    st.write(f"{k}: `{v}`")
            with s2:
                st.caption("**Sentiment**")
                for k, v in (signals.get("sentiment") or {}).items():
                    st.write(f"{k}: `{v}`")
            with s3:
                st.caption("**Smart Money**")
                for k, v in (signals.get("smart_money") or {}).items():
                    st.write(f"{k}: `{v}`")

    # ── Analyst thesis ───────────────────────────────────────────────────
    reasoning = data.get("reasoning", "")
    if reasoning:
        with st.expander("Analyst Thesis", expanded=False):
            st.markdown(reasoning)

    # ── Raw JSON ─────────────────────────────────────────────────────────
    with st.expander("Raw JSON", expanded=False):
        st.json(data)


def render_analyze_result(
    symbol: str,
    exchange: str,
    api_base: str,
    api_key: str,
) -> None:
    """POST /analyze and render the structured card (or error/rate-limit message)."""
    try:
        with httpx.Client(timeout=300.0) as cli:
            resp = cli.post(
                f"{api_base}/analyze",
                headers={"X-API-Key": api_key},
                json={"symbol": symbol, "exchange": exchange},
            )
        if resp.status_code == 429:
            data = resp.json()
            st.warning(f"Rate limit hit. Retry in {data.get('retry_after_seconds', '?')}s.")
            return
        resp.raise_for_status()
        data = resp.json()
        cache_badge = "♻️ cache hit" if data.get("cache_hit") else "🆕 fresh"
        st.caption(f"Source: **{cache_badge}** · "
                   f"Rate limit remaining: {resp.headers.get('X-RateLimit-Remaining', '?')}")
        render_analyze_card(data)
    except Exception as e:
        st.error(f"/analyze failed: {e}")
