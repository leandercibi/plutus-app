from __future__ import annotations

import csv
import logging
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

from plutus.config.logging import get_logger
from plutus.config.settings import Settings, get_settings
from plutus.scheduler import triggers

logger = get_logger(__name__)

_TZ = "Asia/Kolkata"
_NSE500_CSV = Path(__file__).parents[3] / "scripts" / "nse500.csv"


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
        now = datetime.now(tz=UTC).replace(tzinfo=None)
        universe = _load_universe()
        monitor = build_alert_monitor(settings)
        formatter = AlertFormatter()
        ohlcv_chain = OHLCVChain(primary=YFinanceProvider(), fallback=None)
        delivery = DeliveryStubProvider()
        regime_inputs = build_regime_inputs(
            as_of=now.date(),
            vix_provider=VixYFinanceProvider(),
            breadth_provider=BreadthYFinanceProvider(universe),
            fii_dii_provider=FIIDIIStubProvider(),
        )
        init_db()
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
            )
            logger.info("sunday_full_run finished: %s", result.kept)

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
            open_trades = session.execute(
                select(SwingTrade).where(SwingTrade.state.in_(["OPEN", "T1_HIT"]))
            ).scalars().all()
            accum_positions = session.execute(
                select(AccumulationPosition).where(
                    AccumulationPosition.state.in_(["BUILDING", "FULL"])
                )
            ).scalars().all()

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
                    recent = session.execute(
                        select(Notification).where(
                            Notification.symbol == trade.symbol,
                            Notification.kind == "SL_PROXIMITY",
                            Notification.dismissed.is_(False),
                            Notification.created_at >= now - timedelta(hours=2),
                        )
                    ).scalars().first()
                    if recent is None:
                        session.add(Notification(
                            kind="SL_PROXIMITY",
                            severity="URGENT" if sl_distance_pct <= 1.0 else "WARNING",
                            title=f"{trade.symbol} near stop loss",
                            body=f"Price ₹{price:,.2f} is {sl_distance_pct:.1f}% from SL ₹{sl:,.2f}",
                            symbol=trade.symbol,
                            created_at=now,
                        ))

                t1 = float(signal.target_1)
                t1_distance_pct = ((t1 - price) / price) * 100 if price > 0 else 100
                if t1_distance_pct <= 2.0 and trade.state == "OPEN":
                    recent = session.execute(
                        select(Notification).where(
                            Notification.symbol == trade.symbol,
                            Notification.kind == "T1_PROXIMITY",
                            Notification.dismissed.is_(False),
                            Notification.created_at >= now - timedelta(hours=2),
                        )
                    ).scalars().first()
                    if recent is None:
                        session.add(Notification(
                            kind="T1_PROXIMITY",
                            severity="INFO",
                            title=f"{trade.symbol} approaching T1",
                            body=f"Price ₹{price:,.2f} is {t1_distance_pct:.1f}% from T1 ₹{t1:,.2f}",
                            symbol=trade.symbol,
                            created_at=now,
                        ))

            session.flush()
            logger.info(
                "hourly_price_check completed: %d trades, %d accum positions, %d prices fetched",
                len(open_trades), len(accum_positions), len(prices),
            )

    return _run


def build_scheduler(settings: Settings) -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=_TZ)

    scheduler.add_job(
        _build_sunday_callable(settings),
        trigger=triggers.sunday_full_run_trigger(settings.sunday_full_run_hour_ist),
        id="sunday_full_run",
    )
    scheduler.add_job(
        _log_job("monday_revalidation"),
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
        _log_job("daily_freshness_check"),
        trigger=triggers.daily_freshness_trigger(),
        id="daily_freshness_check",
    )
    scheduler.add_job(
        _log_job("weekly_postmortem_publish"),
        trigger=triggers.weekly_postmortem_trigger(),
        id="weekly_postmortem_publish",
    )
    if settings.midweek_mini_screen_enabled:
        scheduler.add_job(
            _log_job("midweek_mini_screen"),
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
