# src/plutus/alerts/monitor.py
"""
Position-aware alert monitor.

Runs every 15 minutes during NSE hours (09:15–15:30 IST) and checks every
open paper trade across ALL portfolios for four alert conditions:

  PRE_SL_WARNING    — LTP within `pre_sl_pct` % of the stop-loss
  TARGET1_HIT       — LTP crossed T1
  TARGET2_HIT       — LTP crossed T2
  TREND_INVALIDATED — daily close < EMA20 for a LONG held > 5 days

Dedup: at most one alert of each type per (trade_id) per `COOLDOWN_HOURS`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from plutus.data.ohlcv import fetch_live_price, fetch_ohlcv, add_indicators
from plutus.db.models import (
    Alert,
    AlertType,
    MockPortfolio,
    PaperTrade,
    Recommendation,
    TradeStatus,
)
from plutus.db.session import SessionLocal

log = logging.getLogger(__name__)

COOLDOWN_HOURS = 1
PRE_SL_PCT_THRESHOLD = 1.0  # warn when LTP is within this % of SL


def _is_nse_hours() -> bool:
    """True if current IST time is within 09:15–15:30 on a weekday."""
    ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    if ist.weekday() >= 5:
        return False
    open_t = ist.replace(hour=9, minute=15, second=0, microsecond=0)
    close_t = ist.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_t <= ist <= close_t


def _already_sent(db, trade_id: int, alert_type: AlertType) -> bool:
    """True if an alert of this type was sent for this trade within COOLDOWN_HOURS."""
    cutoff = datetime.utcnow() - timedelta(hours=COOLDOWN_HOURS)
    return (
        db.query(Alert)
        .filter(
            Alert.trade_id == trade_id,
            Alert.alert_type == alert_type,
            Alert.triggered_at >= cutoff,
        )
        .first()
        is not None
    )


def _fire_alert(
    db,
    trade: PaperTrade,
    alert_type: AlertType,
    message: str,
    ltp: float,
    channels,
) -> None:
    """Persist the alert row and send via all active channels."""
    sent_names = []
    for ch in channels:
        try:
            ok = ch.send(message)
            if ok:
                sent_names.append(ch.name)
        except NotImplementedError:
            pass
        except Exception as exc:
            log.warning("Channel %s failed: %s", ch.name, exc)

    alert = Alert(
        trade_id=trade.id,
        portfolio_id=trade.portfolio_id,
        symbol=trade.symbol,
        alert_type=alert_type,
        message=message,
        channels_sent=sent_names,
        ltp_at_trigger=round(ltp, 2),
    )
    db.add(alert)
    db.commit()
    log.info(
        "Alert fired: %s %s ltp=%.2f channels=%s",
        trade.symbol,
        alert_type.value,
        ltp,
        sent_names,
    )


def _get_ema20(symbol: str) -> Optional[float]:
    """Fetch last EMA20 value for daily bars. Returns None on any error."""
    try:
        df = add_indicators(fetch_ohlcv(symbol, days=40, interval="1d"))
        if "EMA20" in df.columns and not df.empty:
            return float(df["EMA20"].iloc[-1])
    except Exception:
        pass
    return None


def check_open_positions(channels=None) -> int:
    """
    Scan every open trade across all portfolios and fire alerts as needed.
    Returns the count of alerts fired.
    Safe to call outside NSE hours (will still run — callers can gate on _is_nse_hours).
    """
    if channels is None:
        from plutus.alerts.channels import get_active_channels

        channels = get_active_channels()

    fired = 0

    with SessionLocal() as db:
        open_trades = (
            db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.OPEN).all()
        )

        for trade in open_trades:
            try:
                ltp = fetch_live_price(trade.symbol)
            except Exception as exc:
                log.debug("Could not fetch LTP for %s: %s", trade.symbol, exc)
                continue

            # Resolve stop/target from linked recommendation if available
            sl: Optional[float] = None
            t1: Optional[float] = None
            t2: Optional[float] = None
            if trade.linked_recommendation_id:
                rec = db.query(Recommendation).get(trade.linked_recommendation_id)
                if rec:
                    sl = float(rec.stop_loss) if rec.stop_loss else None
                    t1 = float(rec.target1) if rec.target1 else None
                    t2 = float(rec.target2) if rec.target2 else None

            entry = float(trade.entry_price)

            # ── PRE-SL WARNING ───────────────────────────────────────────
            if sl and not _already_sent(db, trade.id, AlertType.PRE_SL_WARNING):
                distance_pct = (ltp - sl) / sl * 100 if sl > 0 else 100.0
                if abs(distance_pct) <= PRE_SL_PCT_THRESHOLD:
                    msg = (
                        f"⚠️ *SL ALERT: {trade.symbol}* approaching stop loss\n"
                        f"LTP: ₹{ltp:,.2f}  |  SL: ₹{sl:,.2f}\n"
                        f"Distance: {distance_pct:+.2f}%\n"
                        f"Consider exit before close."
                    )
                    _fire_alert(db, trade, AlertType.PRE_SL_WARNING, msg, ltp, channels)
                    fired += 1

            # ── TARGET 1 HIT ─────────────────────────────────────────────
            if (
                t1
                and ltp >= t1
                and not _already_sent(db, trade.id, AlertType.TARGET1_HIT)
            ):
                gain_pct = (ltp - entry) / entry * 100
                msg = (
                    f"🎯 *T1 HIT: {trade.symbol}*\n"
                    f"LTP: ₹{ltp:,.2f}  |  T1: ₹{t1:,.2f}\n"
                    f"Gain: {gain_pct:+.2f}%\n"
                    f"Consider partial exit + trail SL to entry."
                )
                _fire_alert(db, trade, AlertType.TARGET1_HIT, msg, ltp, channels)
                fired += 1

            # ── TARGET 2 HIT ─────────────────────────────────────────────
            if (
                t2
                and ltp >= t2
                and not _already_sent(db, trade.id, AlertType.TARGET2_HIT)
            ):
                gain_pct = (ltp - entry) / entry * 100
                msg = (
                    f"🎯🎯 *T2 HIT: {trade.symbol}*\n"
                    f"LTP: ₹{ltp:,.2f}  |  T2: ₹{t2:,.2f}\n"
                    f"Gain: {gain_pct:+.2f}%\n"
                    f"Consider full exit."
                )
                _fire_alert(db, trade, AlertType.TARGET2_HIT, msg, ltp, channels)
                fired += 1

            # ── TREND INVALIDATION ────────────────────────────────────────
            entry_dt = trade.entry_date
            if isinstance(entry_dt, str):
                entry_dt = datetime.fromisoformat(entry_dt)
            days_held = (datetime.utcnow() - entry_dt).days if entry_dt else 0

            if days_held >= 5 and not _already_sent(
                db, trade.id, AlertType.TREND_INVALIDATED
            ):
                ema20 = _get_ema20(trade.symbol)
                if ema20 and ltp < ema20:
                    msg = (
                        f"⚠️ *TREND INVALIDATED: {trade.symbol}*\n"
                        f"LTP: ₹{ltp:,.2f}  |  EMA20: ₹{ema20:,.2f}\n"
                        f"Held {days_held}d — price closed below EMA20.\n"
                        f"Review position for exit."
                    )
                    _fire_alert(
                        db, trade, AlertType.TREND_INVALIDATED, msg, ltp, channels
                    )
                    fired += 1

    return fired


def run_monitor() -> None:
    """Entry point called by the scheduler. Guards on NSE hours."""
    if not _is_nse_hours():
        log.debug("run_monitor: outside NSE hours, skipping")
        return
    fired = check_open_positions()
    log.info("run_monitor complete: %d alerts fired", fired)
