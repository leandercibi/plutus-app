"""
outcomes.py — Daily Mon–Fri outcome tracker (16:30 IST).

For each PENDING recommendation:
  1. Fetch OHLCV bars from signal date → today.
  2. Walk bars in order. Stop-first rule on ambiguous bars.
  3. Mark HIT_T1 / HIT_T2 / STOPPED / WRONG_DIRECTION / EXPIRED.
  4. Record MFE (max favorable excursion %) and MAE (max adverse excursion %).
  5. Write a TradeOutcomesAudit row for calibration reporting.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pytz
import structlog

from plutus.data.ohlcv import fetch_ohlcv
from plutus.db.models import OutcomeVerdict, Recommendation, TradeOutcomesAudit
from plutus.db.session import SessionLocal

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

# Stopped within this many trading days of the signal → WRONG_DIRECTION
_WRONG_DIRECTION_DAYS = 3


def _score_bucket(confidence: float | None) -> str:
    """Map 0-100 composite score to a calibration bucket label."""
    if confidence is None:
        return "UNKNOWN"
    if confidence >= 70:
        return "70-100"
    if confidence >= 55:
        return "55-69"
    if confidence >= 35:
        return "35-54"
    return "0-34"


def _evaluate(rec: Recommendation, today: date) -> Optional[dict]:
    """
    Walk OHLCV bars and determine the outcome.

    Returns a dict with keys:
        outcome, outcome_pct, exit_price, exit_date,
        mfe_pct, mae_pct, trading_days_held
    or None if data is unavailable / recommendation is still open.
    """
    fill = float(rec.entry_mid or rec.entry_low or 0)
    stop = float(rec.stop_loss or 0)
    t1 = float(rec.target1 or 0)
    t2 = float(rec.target2 or t1)
    hold_max = int(rec.hold_days_max or 10)

    if fill <= 0 or stop <= 0 or t1 <= 0:
        return None

    signal_date: date = rec.created_at.date() if rec.created_at else today
    days_needed = max((today - signal_date).days + 5, 20)

    try:
        df = fetch_ohlcv(rec.symbol, days=days_needed, interval="1d")
    except Exception as exc:
        logger.debug("outcome_fetch_failed", symbol=rec.symbol, error=str(exc))
        return None

    if df is None or df.empty:
        return None

    # Only bars strictly after the signal date
    df = df[df.index.normalize() > str(signal_date)].copy()
    if df.empty:
        return None

    mfe = 0.0
    mae = 0.0
    trading_day = 0

    for bar_ts, row in df.iterrows():
        bar_date: date = bar_ts.date() if hasattr(bar_ts, "date") else bar_ts
        if bar_date > today:
            break

        trading_day += 1
        high = float(row.get("High", row.get("high", fill)))
        low = float(row.get("Low", row.get("low", fill)))
        close = float(row.get("Close", row.get("close", fill)))

        # Running excursion stats
        mfe = max(mfe, (high - fill) / fill * 100)
        mae = max(mae, (fill - low) / fill * 100)

        # ── Stop-first rule: check SL before targets on same bar ─────────────
        if low <= stop:
            wrong = trading_day <= _WRONG_DIRECTION_DAYS
            verdict = (
                OutcomeVerdict.WRONG_DIRECTION if wrong else OutcomeVerdict.STOPPED
            )
            return {
                "outcome": verdict,
                "outcome_pct": (stop - fill) / fill * 100,
                "exit_price": stop,
                "exit_date": bar_date,
                "mfe_pct": mfe,
                "mae_pct": mae,
                "trading_days_held": trading_day,
            }

        if t2 and high >= t2:
            return {
                "outcome": OutcomeVerdict.HIT_T2,
                "outcome_pct": (t2 - fill) / fill * 100,
                "exit_price": t2,
                "exit_date": bar_date,
                "mfe_pct": mfe,
                "mae_pct": mae,
                "trading_days_held": trading_day,
            }

        if high >= t1:
            return {
                "outcome": OutcomeVerdict.HIT_T1,
                "outcome_pct": (t1 - fill) / fill * 100,
                "exit_price": t1,
                "exit_date": bar_date,
                "mfe_pct": mfe,
                "mae_pct": mae,
                "trading_days_held": trading_day,
            }

        if trading_day >= hold_max:
            return {
                "outcome": OutcomeVerdict.EXPIRED,
                "outcome_pct": (close - fill) / fill * 100,
                "exit_price": close,
                "exit_date": bar_date,
                "mfe_pct": mfe,
                "mae_pct": mae,
                "trading_days_held": trading_day,
            }

    return None  # Still open


def track_recommendation_outcomes(db_session=None) -> dict:
    """
    Walk-forward all PENDING recommendations and mark outcomes.
    Safe to call ad-hoc or via the Mon–Fri 16:30 IST scheduler job.

    Returns {"total": int, "updated": int, "skipped": int}.
    """
    close_session = db_session is None
    if close_session:
        db_session = SessionLocal()

    today = datetime.now(IST).date()
    updated = skipped = 0

    try:
        pending = (
            db_session.query(Recommendation)
            .filter(Recommendation.outcome == OutcomeVerdict.PENDING)
            .all()
        )
        total = len(pending)
        logger.info("outcome_tracker_start", pending=total, date=str(today))

        for rec in pending:
            try:
                result = _evaluate(rec, today)
                if result is None:
                    skipped += 1
                    continue

                rec.outcome = result["outcome"]
                rec.outcome_pct = result["outcome_pct"]
                rec.outcome_exit_price = result["exit_price"]
                rec.outcome_exit_date = result["exit_date"]
                rec.outcome_tracked_at = datetime.utcnow()
                rec.mfe_pct = result["mfe_pct"]
                rec.mae_pct = result["mae_pct"]

                db_session.add(
                    TradeOutcomesAudit(
                        recommendation_id=rec.id,
                        symbol=rec.symbol,
                        outcome=result["outcome"],
                        outcome_pct=result["outcome_pct"],
                        exit_date=result["exit_date"],
                        mfe_pct=result["mfe_pct"],
                        mae_pct=result["mae_pct"],
                        trading_days_held=result["trading_days_held"],
                        score_bucket=_score_bucket(rec.confidence),
                        bundle_used=rec.strategy_used,
                        regime_at_signal=None,
                        created_at=datetime.utcnow(),
                    )
                )
                updated += 1

            except Exception as exc:
                logger.warning(
                    "outcome_tracker_rec_failed", rec_id=rec.id, error=str(exc)
                )
                skipped += 1

        db_session.commit()
        logger.info(
            "outcome_tracker_done", total=total, updated=updated, skipped=skipped
        )
        return {"total": total, "updated": updated, "skipped": skipped}

    except Exception as exc:
        db_session.rollback()
        logger.error("outcome_tracker_failed", error=str(exc))
        raise
    finally:
        if close_session:
            db_session.close()
