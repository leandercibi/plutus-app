from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from plutus.alerts.channels import AlertMessage, AlertResult
from plutus.alerts.monitor import AlertMonitor
from plutus.config.settings import Settings
from plutus.db.models import Base
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
    def __init__(self, name: str) -> None:
        self.name = name
        self.sent: list[AlertMessage] = []

    def send(self, message: AlertMessage) -> AlertResult:
        self.sent.append(message)
        return AlertResult(success=True, channel=self.name, message_id="1")


def _msg(kind: str, symbol: str = "INFY") -> AlertMessage:
    return AlertMessage(
        kind=kind,  # type: ignore[arg-type]
        symbol=symbol,
        title="t",
        body_md="b",
        severity="WARNING",
        deduplication_key=f"{symbol}:{kind}",
    )


def test_cooldown_respected_for_warning(session: Session) -> None:
    ch = _SpyChannel("spy")
    monitor = AlertMonitor([ch], CooldownPolicy(Settings(_env_file=None)))
    now = datetime(2025, 1, 1, 10, 0)
    monitor.emit(_msg("SL_WARNING"), now, session)
    session.commit()
    monitor.emit(_msg("SL_WARNING"), now + timedelta(minutes=5), session)
    session.commit()
    assert len(ch.sent) == 1  # second suppressed within cooldown


@pytest.mark.hallmark
def test_sl_breach_always_fires(session: Session) -> None:
    """A16 hallmark: SL_WARNING just fired -> SL_BREACH still fires immediately."""
    ch = _SpyChannel("spy")
    monitor = AlertMonitor([ch], CooldownPolicy(Settings(_env_file=None)))
    now = datetime(2025, 1, 1, 10, 0)
    monitor.emit(_msg("SL_WARNING"), now, session)
    session.commit()
    results = monitor.emit(_msg("SL_BREACH"), now + timedelta(minutes=1), session)
    session.commit()
    assert len(results) == 1
    assert results[0].success
    breach_sent = [m for m in ch.sent if m.kind == "SL_BREACH"]
    assert len(breach_sent) == 1


def test_dedup_across_channels_counts_once(session: Session) -> None:
    a, b = _SpyChannel("a"), _SpyChannel("b")
    monitor = AlertMonitor([a, b], CooldownPolicy(Settings(_env_file=None)))
    now = datetime(2025, 1, 1, 10, 0)
    monitor.emit(_msg("T1_HIT"), now, session)
    session.commit()
    # both channels got it, cooldown recorded once
    assert len(a.sent) == 1
    assert len(b.sent) == 1
    monitor.emit(_msg("T1_HIT"), now + timedelta(minutes=5), session)
    session.commit()
    assert len(a.sent) == 1  # suppressed
