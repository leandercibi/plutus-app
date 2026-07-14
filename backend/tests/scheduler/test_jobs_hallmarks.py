from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from plutus.alerts.channels import AlertMessage, AlertResult
from plutus.alerts.formatter import AlertFormatter
from plutus.alerts.monitor import AlertMonitor
from plutus.config.settings import Settings
from plutus.db.models import Base
from plutus.scheduler.jobs import (
    RevalidationCandidate,
    daily_freshness_job,
    midweek_mini_screen_job,
    monday_revalidation_job,
)
from plutus.swing.exits.cooldown import CooldownPolicy


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


class _SpyChannel:
    name = "spy"

    def __init__(self) -> None:
        self.sent: list[AlertMessage] = []

    def send(self, message: AlertMessage) -> AlertResult:
        self.sent.append(message)
        return AlertResult(success=True, channel=self.name, message_id="1")


def _monitor(ch: _SpyChannel) -> AlertMonitor:
    return AlertMonitor([ch], CooldownPolicy(Settings(_env_file=None)))


@pytest.mark.hallmark
def test_monday_revalidation_kills_on_weekend_gap(session: Session) -> None:
    """A15 hallmark: a weekend gap > 1 ATR kills the signal and the alert names the reason."""
    ch = _SpyChannel()
    settings = Settings(_env_file=None)
    candidates = [
        RevalidationCandidate(
            symbol="INFY",
            entry=Decimal("100"),
            monday_open=Decimal("108"),
            atr=Decimal("5"),
        ),  # 8-point gap > 1*5 ATR -> kill
        RevalidationCandidate(
            symbol="TCS",
            entry=Decimal("100"),
            monday_open=Decimal("101"),
            atr=Decimal("5"),
        ),  # within tolerance -> keep
    ]
    result = monday_revalidation_job(
        candidates,
        _monitor(ch),
        AlertFormatter(),
        settings,
        datetime(2025, 1, 6, 9, 10),
        session,
    )
    session.commit()
    assert "INFY" in [s for s, _ in result.killed]
    assert "TCS" in result.kept
    assert any(m.kind == "MONDAY_REVALIDATION" for m in ch.sent)


@pytest.mark.hallmark
def test_freshness_aborts_and_alerts(session: Session) -> None:
    """B11 hallmark: a stale candle aborts the run and emits an URGENT alert."""
    ch = _SpyChannel()
    settings = Settings(_env_file=None)  # freshness enabled by default
    result = daily_freshness_job(
        latest_candle_date=date(2025, 1, 1),  # stale vs run date
        run_date=date(2025, 1, 10),
        monitor=_monitor(ch),
        settings=settings,
        now=datetime(2025, 1, 10, 9, 5),
        session=session,
    )
    session.commit()
    assert result.status == "ABORTED"
    assert result.aborted_reason is not None
    assert any(m.severity == "URGENT" for m in ch.sent)


def test_midweek_gated_off_is_noop() -> None:
    """B18: midweek mini-screen is a no-op when the flag is off (default)."""
    result = midweek_mini_screen_job(Settings(_env_file=None))
    assert result.status == "OK"
    assert result.aborted_reason == "disabled"


def test_midweek_enabled_runs() -> None:
    result = midweek_mini_screen_job(Settings(_env_file=None, midweek_mini_screen_enabled=True))
    assert result.status == "OK"
    assert result.aborted_reason is None
