from __future__ import annotations

import csv
import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler

from plutus.config.logging import get_logger
from plutus.config.settings import Settings, get_settings
from plutus.scheduler import triggers

logger = get_logger(__name__)

_TZ = "Asia/Kolkata"
_NSE500_CSV = Path(__file__).parents[1] / "data" / "nse500.csv"


def _load_universe() -> list[str]:
    try:
        with open(_NSE500_CSV) as f:
            rows = list(csv.DictReader(f))
            return [r["symbol"].strip() for r in rows if r.get("symbol")]
    except Exception as exc:
        logger.warning("Could not load nse500.csv: %s; using fallback", exc)
        return ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]


def _build_sunday_callable(settings: Settings):  # type: ignore[no-untyped-def]
    try:
        from plutus.alerts.factory import build_alert_monitor
        from plutus.alerts.formatter import AlertFormatter
        from plutus.data.ohlcv import OHLCVChain
        from plutus.data.providers.breadth_provider import BreadthYFinanceProvider
        from plutus.data.providers.delivery_stub import DeliveryStubProvider
        from plutus.data.providers.fii_dii_provider import FIIDIIStubProvider
        from plutus.data.providers.regime_builder import build_regime_inputs
        from plutus.data.providers.vix_provider import VixYFinanceProvider
        from plutus.data.providers.yfinance_provider import YFinanceProvider
        from plutus.db.init_db import init_db
        from plutus.db.session import session_scope
        from plutus.scheduler.jobs import sunday_full_run_job
    except ImportError as exc:
        logger.warning("Sunday job deps unavailable (%s); using log stub", exc)
        return _log_job("sunday_full_run")

    def _run() -> None:
        import uuid

        from plutus.db.models import RunLogRow

        now = datetime.now(tz=UTC).replace(tzinfo=None)
        run_id = f"sun-{uuid.uuid4().hex[:8]}"

        # Run-log start/end each use their own transaction so the row persists
        # in the dashboard even if the job aborts or crashes mid-run.
        try:
            with session_scope() as s:
                s.add(RunLogRow(run_id=run_id, job_name="sunday_full_run", started_at=now))
        except Exception:
            logger.warning("run-log start write failed", exc_info=True)

        universe = _load_universe()
        monitor = build_alert_monitor(settings)
        formatter = AlertFormatter()
        ohlcv_chain = OHLCVChain(primary=YFinanceProvider(), fallback=None)
        delivery = DeliveryStubProvider()
        regime_inputs = build_regime_inputs(
            as_of=now.date(),
            vix_provider=VixYFinanceProvider(),
            breadth_provider=BreadthYFinanceProvider(),
            fii_dii_provider=FIIDIIStubProvider(),
        )
        init_db()
        status = "FAILED"
        details: dict[str, Any] = {}
        try:
            with session_scope() as session:
                result = sunday_full_run_job(
                    universe=universe,
                    ohlcv_chain=ohlcv_chain,
                    delivery_provider=delivery,
                    regime_inputs=regime_inputs,
                    session=session,
                    settings=settings,
                    monitor=monitor,
                    formatter=formatter,
                    now=now,
                    run_id=run_id,
                )
                status = result.status if result.status in ("OK", "ABORTED") else "FAILED"
                details = {"kept": result.kept, "aborted_reason": result.aborted_reason}
                logger.info("sunday_full_run finished: %s", result.kept)
        except Exception:
            logger.exception("sunday_full_run crashed")
        finally:
            try:
                with session_scope() as s:
                    row = s.get(RunLogRow, run_id)
                    if row is not None:
                        row.ended_at = datetime.now(tz=UTC).replace(tzinfo=None)
                        row.status = status
                        row.details_json = details
            except Exception:
                logger.warning("run-log end write failed", exc_info=True)

    return _run


def _build_exit_monitor_callable(settings: Settings):  # type: ignore[no-untyped-def]
    try:
        from plutus.alerts.factory import build_alert_monitor
        from plutus.alerts.formatter import AlertFormatter
        from plutus.data.ohlcv import OHLCVChain
        from plutus.data.providers.yfinance_provider import YFinanceProvider
        from plutus.db.session import session_scope
        from plutus.scheduler.jobs import daily_exit_monitor_job
    except ImportError as exc:
        logger.warning("Exit monitor deps unavailable (%s); using log stub", exc)
        return _log_job("daily_exit_monitor")

    def _run() -> None:
        now = datetime.now(tz=UTC).replace(tzinfo=None)
        monitor = build_alert_monitor(settings)
        formatter = AlertFormatter()
        ohlcv_chain = OHLCVChain(primary=YFinanceProvider(), fallback=None)
        with session_scope() as session:
            result = daily_exit_monitor_job(
                session=session,
                settings=settings,
                monitor=monitor,
                formatter=formatter,
                now=now,
                ohlcv_chain=ohlcv_chain,
            )
            logger.info("daily_exit_monitor finished: %s", result.status)

    return _run


def _build_hourly_price_check_callable(settings: Settings):  # type: ignore[no-untyped-def]
    try:
        from plutus.db.init_db import init_db
        from plutus.db.session import session_scope
    except ImportError as exc:
        logger.warning("Hourly price check deps unavailable (%s); using log stub", exc)
        return _log_job("hourly_price_check")

    def _run() -> None:
        from datetime import timedelta

        from sqlalchemy import select

        from plutus.api.shared import _fetch_live_prices
        from plutus.db.models import (
            AccumulationPosition,
            Notification,
            SwingSignal,
            SwingTrade,
        )

        now = datetime.now(tz=UTC).replace(tzinfo=None)
        init_db()
        with session_scope() as session:
            open_trades = (
                session.execute(select(SwingTrade).where(SwingTrade.state.in_(["OPEN", "T1_HIT"])))
                .scalars()
                .all()
            )
            accum_positions = (
                session.execute(
                    select(AccumulationPosition).where(
                        AccumulationPosition.state.in_(["BUILDING", "FULL"])
                    )
                )
                .scalars()
                .all()
            )

            symbols = {t.symbol for t in open_trades}
            symbols.update(p.symbol for p in accum_positions)

            prices = _fetch_live_prices(symbols, settings, session)

            for trade in open_trades:
                signal = session.get(SwingSignal, trade.signal_id)
                if signal is None:
                    continue
                price = prices.get(trade.symbol)
                if price is None or price <= 0:
                    continue

                sl = float(signal.stop_loss)
                sl_distance_pct = ((price - sl) / price) * 100

                if sl_distance_pct <= 3.0:
                    recent = (
                        session.execute(
                            select(Notification).where(
                                Notification.symbol == trade.symbol,
                                Notification.kind == "SL_PROXIMITY",
                                Notification.dismissed.is_(False),
                                Notification.created_at >= now - timedelta(hours=2),
                            )
                        )
                        .scalars()
                        .first()
                    )
                    if recent is None:
                        session.add(
                            Notification(
                                kind="SL_PROXIMITY",
                                severity="URGENT" if sl_distance_pct <= 1.0 else "WARNING",
                                title=f"{trade.symbol} near stop loss",
                                body=f"Price ₹{price:,.2f} is {sl_distance_pct:.1f}% from SL ₹{sl:,.2f}",
                                symbol=trade.symbol,
                                created_at=now,
                            )
                        )

                t1 = float(signal.target_1)
                t1_distance_pct = ((t1 - price) / price) * 100 if price > 0 else 100
                if t1_distance_pct <= 2.0 and trade.state == "OPEN":
                    recent = (
                        session.execute(
                            select(Notification).where(
                                Notification.symbol == trade.symbol,
                                Notification.kind == "T1_PROXIMITY",
                                Notification.dismissed.is_(False),
                                Notification.created_at >= now - timedelta(hours=2),
                            )
                        )
                        .scalars()
                        .first()
                    )
                    if recent is None:
                        session.add(
                            Notification(
                                kind="T1_PROXIMITY",
                                severity="INFO",
                                title=f"{trade.symbol} approaching T1",
                                body=f"Price ₹{price:,.2f} is {t1_distance_pct:.1f}% from T1 ₹{t1:,.2f}",
                                symbol=trade.symbol,
                                created_at=now,
                            )
                        )

            session.flush()
            logger.info(
                "hourly_price_check completed: %d trades, %d accum positions, %d prices fetched",
                len(open_trades),
                len(accum_positions),
                len(prices),
            )

    return _run


# --------------------------------------------------------------------------- #
# Shared run-log wrapper + small helpers
# --------------------------------------------------------------------------- #


def _atr14(df) -> Decimal:  # type: ignore[no-untyped-def]
    """14-period ATR from OHLC candles; falls back to mean(high-low)."""
    import pandas as pd

    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev).abs(), (low - prev).abs()], axis=1).max(
        axis=1
    )
    atr = float(tr.rolling(14).mean().iloc[-1])
    if atr != atr or atr <= 0:  # NaN or non-positive
        atr = float((high - low).tail(14).mean())
    return Decimal(str(round(max(atr, 0.01), 2)))


def _latest_candle_date(df) -> date:  # type: ignore[no-untyped-def]
    """Most recent date in an OHLCV df (supports a 'date' column or a DatetimeIndex)."""
    import pandas as pd

    if "date" in df.columns:
        return pd.Timestamp(df["date"].iloc[-1]).date()
    return pd.Timestamp(df.index[-1]).date()


def _run_with_runlog(job_name: str, work) -> None:  # type: ignore[no-untyped-def]
    """Run ``work(session)`` wrapped in a RunLogRow (start/end, own transactions).

    ``work`` may return a details dict (optionally with a ``status`` key) and may
    raise — a crash is recorded as FAILED so the scheduler keeps running.
    """
    import uuid

    from plutus.db.models import RunLogRow
    from plutus.db.session import session_scope

    started = datetime.now(tz=UTC).replace(tzinfo=None)
    run_id = f"{job_name[:8]}-{uuid.uuid4().hex[:8]}"
    try:
        with session_scope() as s:
            s.add(RunLogRow(run_id=run_id, job_name=job_name, started_at=started))
    except Exception:
        logger.warning("run-log start failed for %s", job_name, exc_info=True)

    status = "FAILED"
    details: dict[str, Any] = {}
    try:
        with session_scope() as session:
            result = work(session)
            if isinstance(result, dict):
                status = str(result.pop("status", "OK"))
                details = result
            else:
                status = "OK"
    except Exception as exc:
        logger.exception("%s crashed", job_name)
        details = {"error": str(exc)}
    finally:
        try:
            with session_scope() as s:
                row = s.get(RunLogRow, run_id)
                if row is not None:
                    row.ended_at = datetime.now(tz=UTC).replace(tzinfo=None)
                    row.status = status
                    row.details_json = details
        except Exception:
            logger.warning("run-log end failed for %s", job_name, exc_info=True)


def _build_monday_revalidation_callable(settings: Settings):  # type: ignore[no-untyped-def]
    """A15 — re-validate the latest Sunday signals against Monday's open."""
    try:
        from sqlalchemy import select

        from plutus.alerts.factory import build_alert_monitor
        from plutus.alerts.formatter import AlertFormatter
        from plutus.data.providers.yfinance_provider import YFinanceProvider
        from plutus.db.models import SwingSignal
        from plutus.scheduler.jobs import RevalidationCandidate, monday_revalidation_job
    except ImportError as exc:
        logger.warning("Monday revalidation deps unavailable (%s); using log stub", exc)
        return _log_job("monday_revalidation")

    def _run() -> None:
        def work(session):  # type: ignore[no-untyped-def]
            now = datetime.now(tz=UTC).replace(tzinfo=None)
            latest = (
                session.execute(
                    select(SwingSignal).order_by(SwingSignal.created_at.desc()).limit(1)
                )
                .scalars()
                .first()
            )
            if latest is None:
                return {"status": "OK", "note": "no signals to revalidate"}
            sigs = (
                session.execute(select(SwingSignal).where(SwingSignal.run_id == latest.run_id))
                .scalars()
                .all()
            )

            provider = YFinanceProvider()
            end = now.date()
            start = end - timedelta(days=45)
            candidates = []
            for sig in sigs:
                try:
                    df = provider.fetch(sig.symbol, start, end)
                    if df is None or df.empty or len(df) < 15:
                        continue
                    candidates.append(
                        RevalidationCandidate(
                            symbol=sig.symbol,
                            entry=sig.entry,
                            monday_open=Decimal(str(round(float(df["open"].iloc[-1]), 2))),
                            atr=_atr14(df),
                            hard_kill_fires=False,
                        )
                    )
                except Exception:
                    logger.warning("reval candidate failed for %s", sig.symbol, exc_info=True)

            monitor = build_alert_monitor(settings)
            formatter = AlertFormatter()
            result = monday_revalidation_job(candidates, monitor, formatter, settings, now, session)
            return {
                "status": result.status,
                "run_id": latest.run_id,
                "n_candidates": len(candidates),
                "kept": result.kept,
                "killed": [list(k) for k in result.killed],
            }

        _run_with_runlog("monday_revalidation", work)

    return _run


def _build_daily_freshness_callable(settings: Settings):  # type: ignore[no-untyped-def]
    """B11 — assert market-data freshness; URGENT alert + ABORTED on stale data."""
    try:
        from plutus.alerts.factory import build_alert_monitor
        from plutus.data.providers.market_data import fetch_nifty_candles
        from plutus.scheduler.jobs import daily_freshness_job
    except ImportError as exc:
        logger.warning("Freshness deps unavailable (%s); using log stub", exc)
        return _log_job("daily_freshness_check")

    def _run() -> None:
        def work(session):  # type: ignore[no-untyped-def]
            now = datetime.now(tz=UTC).replace(tzinfo=None)
            run_date = now.date()
            nifty = fetch_nifty_candles(end=run_date)
            latest = (
                _latest_candle_date(nifty) if nifty is not None and not nifty.empty else run_date
            )
            monitor = build_alert_monitor(settings)
            result = daily_freshness_job(latest, run_date, monitor, settings, now, session)
            return {
                "status": result.status,
                "latest_candle_date": str(latest),
                "aborted_reason": result.aborted_reason,
            }

        _run_with_runlog("daily_freshness_check", work)

    return _run


def _build_midweek_mini_callable(settings: Settings):  # type: ignore[no-untyped-def]
    """B18 — midweek mini-screen (gated by settings.midweek_mini_screen_enabled)."""
    try:
        from plutus.scheduler.jobs import midweek_mini_screen_job
    except ImportError as exc:
        logger.warning("Midweek deps unavailable (%s); using log stub", exc)
        return _log_job("midweek_mini_screen")

    def _run() -> None:
        def work(_session):  # type: ignore[no-untyped-def]
            result = midweek_mini_screen_job(settings)
            return {"status": result.status, "note": result.aborted_reason or "ran"}

        _run_with_runlog("midweek_mini_screen", work)

    return _run


def _build_weekly_postmortem_callable(settings: Settings):  # type: ignore[no-untyped-def]
    """Publish the weekly postmortem row (swing vs Nifty, drawdown, trade count)."""
    try:
        from sqlalchemy import select

        from plutus.data.providers.market_data import fetch_nifty_candles
        from plutus.db.models import SwingTrade, WeeklyPostmortem
    except ImportError as exc:
        logger.warning("Postmortem deps unavailable (%s); using log stub", exc)
        return _log_job("weekly_postmortem_publish")

    def _run() -> None:
        def work(session):  # type: ignore[no-untyped-def]
            now = datetime.now(tz=UTC).replace(tzinfo=None)
            week_ending = now.date()
            since = now - timedelta(days=7)
            closed = (
                session.execute(
                    select(SwingTrade).where(
                        SwingTrade.state.in_(["CLOSED_WIN", "CLOSED_LOSS"]),
                        SwingTrade.closed_at >= since,
                    )
                )
                .scalars()
                .all()
            )
            realized = [t.realized_R for t in closed if t.realized_R is not None]

            # Portfolio return ≈ ΣR × risk-per-trade (each trade risks that % of capital).
            risk = settings.risk_per_trade_pct
            swing_return = sum(realized) * risk * 100 if realized else 0.0
            # Drawdown from the intra-week cumulative-return path.
            cum = peak = dd = 0.0
            for r in realized:
                cum += r * risk * 100
                peak = max(peak, cum)
                dd = max(dd, peak - cum)

            nifty_ret = 0.0
            try:
                nifty = fetch_nifty_candles(end=week_ending)
                closes = nifty["close"]
                if len(closes) >= 6:
                    nifty_ret = float((closes.iloc[-1] - closes.iloc[-6]) / closes.iloc[-6] * 100)
            except Exception:
                logger.warning("postmortem nifty fetch failed", exc_info=True)

            row = session.get(WeeklyPostmortem, week_ending)
            if row is None:
                row = WeeklyPostmortem(week_ending=week_ending)
                session.add(row)
            row.swing_return_pct = round(swing_return, 2)
            row.nifty_return_pct = round(nifty_ret, 2)
            # Baselines need a full simulation; left neutral until that path is wired.
            row.regime_switched_return_pct = 0.0
            row.random_baseline_return_pct = 0.0
            row.n_swing_trades_closed = len(closed)
            row.drawdown_pct = round(dd, 2)
            row.report_md_path = f"reports/weekly/{week_ending.isoformat()}.md"
            return {
                "status": "OK",
                "n_trades_closed": len(closed),
                "swing_return_pct": round(swing_return, 2),
                "nifty_return_pct": round(nifty_ret, 2),
            }

        _run_with_runlog("weekly_postmortem_publish", work)

    return _run


def build_scheduler(settings: Settings) -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=_TZ)

    scheduler.add_job(
        _build_sunday_callable(settings),
        trigger=triggers.sunday_full_run_trigger(settings.sunday_full_run_hour_ist),
        id="sunday_full_run",
    )
    scheduler.add_job(
        _build_monday_revalidation_callable(settings),
        trigger=triggers.monday_revalidation_trigger(
            settings.monday_revalidation_hour_ist,
            settings.monday_revalidation_minute_ist,
        ),
        id="monday_revalidation",
    )
    scheduler.add_job(
        _build_exit_monitor_callable(settings),
        trigger=triggers.daily_exit_monitor_trigger(settings.daily_exit_monitor_minutes),
        id="daily_exit_monitor",
    )
    scheduler.add_job(
        _build_daily_freshness_callable(settings),
        trigger=triggers.daily_freshness_trigger(),
        id="daily_freshness_check",
    )
    scheduler.add_job(
        _build_weekly_postmortem_callable(settings),
        trigger=triggers.weekly_postmortem_trigger(),
        id="weekly_postmortem_publish",
    )
    if settings.midweek_mini_screen_enabled:
        scheduler.add_job(
            _build_midweek_mini_callable(settings),
            trigger=triggers.midweek_mini_screen_trigger(),
            id="midweek_mini_screen",
        )
    scheduler.add_job(
        _build_hourly_price_check_callable(settings),
        trigger=triggers.hourly_price_check_trigger(),
        id="hourly_price_check",
    )
    return scheduler


def _log_job(name: str):  # type: ignore[no-untyped-def]
    def _run() -> None:
        logger.info("scheduled job fired", extra={"job": name})

    return _run


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    scheduler = build_scheduler(settings)
    logger.info(
        "scheduler starting",
        extra={"jobs": [j.id for j in scheduler.get_jobs()], "tz": _TZ},
    )
    scheduler.start()


if __name__ == "__main__":
    main()
