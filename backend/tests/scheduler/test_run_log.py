from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from plutus.db.models import Base
from plutus.scheduler.run_log import RunLog


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


def test_start_end_pair_persisted(session: Session) -> None:
    log = RunLog(session)
    rid = log.start("sunday_full_run", datetime(2025, 1, 5, 19, 0), "run-1")
    log.end(rid, "OK", {"signals": 12}, datetime(2025, 1, 5, 19, 30))
    session.commit()
    rows = log.history("sunday_full_run")
    assert len(rows) == 1
    assert rows[0].status == "OK"
    assert rows[0].details_json == {"signals": 12}


def test_history_returns_most_recent_first(session: Session) -> None:
    log = RunLog(session)
    log.start("daily_exit_monitor", datetime(2025, 1, 1, 9, 30), "r1")
    log.start("daily_exit_monitor", datetime(2025, 1, 2, 9, 30), "r2")
    session.commit()
    rows = log.history("daily_exit_monitor")
    assert [r.run_id for r in rows] == ["r2", "r1"]
