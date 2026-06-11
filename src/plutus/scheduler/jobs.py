from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from plutus.alerts.channels import AlertMessage
from plutus.alerts.formatter import AlertFormatter
from plutus.alerts.monitor import AlertMonitor
from plutus.config.settings import Settings
from plutus.data.freshness import FreshnessError, assert_freshness
from plutus.swing.entries.monday_revalidation import MondayRevalidation


@dataclass(frozen=True)
class RevalidationCandidate:
    symbol: str
    entry: Decimal
    monday_open: Decimal
    atr: Decimal
    hard_kill_fires: bool = False


@dataclass(frozen=True)
class JobResult:
    job_name: str
    status: str  # "OK" | "ABORTED"
    kept: list[str] = field(default_factory=list)
    killed: list[tuple[str, str]] = field(default_factory=list)
    aborted_reason: str | None = None


def monday_revalidation_job(
    candidates: list[RevalidationCandidate],
    monitor: AlertMonitor,
    formatter: AlertFormatter,
    settings: Settings,
    now: datetime,
    session: Session,
) -> JobResult:
    """A15 — re-run entry validation on Monday open; emit kept/killed alert."""
    reval = MondayRevalidation(settings)
    kept: list[str] = []
    killed: list[tuple[str, str]] = []
    for c in candidates:
        outcome = reval.reevaluate(
            sunday_signal=_StubSignal(c.symbol, c.entry),
            monday_open=c.monday_open,
            atr=c.atr,
            hard_kill_fires=c.hard_kill_fires,
        )
        if outcome.keep:
            kept.append(c.symbol)
        else:
            killed.append((c.symbol, outcome.reason))

    msg = formatter.format_monday_revalidation(kept, killed, now.date())
    monitor.emit(msg, now, session)
    return JobResult("monday_revalidation", "OK", kept=kept, killed=killed)


def daily_freshness_job(
    latest_candle_date: date,
    run_date: date,
    monitor: AlertMonitor,
    settings: Settings,
    now: datetime,
    session: Session,
) -> JobResult:
    """B11 — abort the day's runs and alert URGENT on stale data."""
    try:
        assert_freshness(
            latest_candle_date, run_date, settings.freshness_assert_enabled
        )
    except FreshnessError as exc:
        monitor.emit(
            AlertMessage(
                kind="SL_WARNING",
                symbol=None,
                title="DATA FRESHNESS FAILURE",
                body_md=str(exc),
                severity="URGENT",
                deduplication_key=f"FRESHNESS:{run_date.isoformat()}",
            ),
            now,
            session,
        )
        return JobResult("daily_freshness_check", "ABORTED", aborted_reason=str(exc))
    return JobResult("daily_freshness_check", "OK")


def midweek_mini_screen_job(settings: Settings) -> JobResult:
    """B18 — gated by settings.midweek_mini_screen_enabled; no-op when disabled."""
    if not settings.midweek_mini_screen_enabled:
        return JobResult("midweek_mini_screen", "OK", aborted_reason="disabled")
    # When enabled, runs Breakout + PEAD only (wired in a later phase).
    return JobResult("midweek_mini_screen", "OK")


@dataclass(frozen=True)
class _StubSignal:
    symbol: str
    entry: Decimal
