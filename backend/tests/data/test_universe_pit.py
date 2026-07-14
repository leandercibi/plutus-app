from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from plutus.config.settings import Settings
from plutus.data.universe import (
    UniverseSnapshot,
    build_universe_snapshot,
    get_universe_at,
)
from plutus.db.models import Base


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


def _liquid_history(close: float, volume: int, n: int, end: date) -> pd.DataFrame:
    idx = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    return pd.DataFrame(
        {
            "open": [close] * n,
            "high": [close + 1] * n,
            "low": [close - 1] * n,
            "close": [close] * n,
            "volume": [volume] * n,
        },
        index=idx,
    )


def _make_lookup(frames: dict[str, pd.DataFrame]):  # type: ignore[no-untyped-def]
    def lookup(symbol: str, as_of: date) -> pd.DataFrame:
        df = frames.get(symbol)
        if df is None:
            return pd.DataFrame()
        return df[df.index <= pd.Timestamp(as_of)]

    return lookup


@pytest.mark.hallmark
def test_membership_matches_frozen_fixture(settings_floor: Settings, session: Session) -> None:
    as_of = date(2025, 6, 30)
    # LIQUID: 300 days history, 100*1_000_000 traded value = 1e8 >= 5e7 floor
    # THIN: 300 days but only 100*100_000 = 1e7 < floor
    # SHORT: liquid but only 50 days history < 252 min
    frames = {
        "LIQUID": _liquid_history(100.0, 1_000_000, 300, as_of),
        "THIN": _liquid_history(100.0, 100_000, 300, as_of),
        "SHORT": _liquid_history(100.0, 1_000_000, 50, as_of),
    }
    snap = build_universe_snapshot(
        as_of,
        seed=["LIQUID", "THIN", "SHORT"],
        ohlcv_lookup=_make_lookup(frames),
        session=session,
        settings=settings_floor,
    )
    assert isinstance(snap, UniverseSnapshot)
    assert snap.members == frozenset({"LIQUID"})
    assert "THIN" in snap.rejected_for_liquidity


@pytest.mark.hallmark
def test_pit_lookup_differs_across_dates(settings_floor: Settings, session: Session) -> None:
    today = date(2025, 6, 30)
    year_ago = date(2024, 6, 30)
    # ACME becomes liquid only recently: liquid as of today, thin a year ago
    liquid_now = _liquid_history(100.0, 1_000_000, 400, today)
    frames = {"ACME": liquid_now}
    lookup = _make_lookup(frames)

    # build a snapshot a year ago: only ~135 trading days exist before year_ago -> too short
    build_universe_snapshot(
        year_ago,
        seed=["ACME"],
        ohlcv_lookup=lookup,
        session=session,
        settings=settings_floor,
    )
    build_universe_snapshot(
        today,
        seed=["ACME"],
        ohlcv_lookup=lookup,
        session=session,
        settings=settings_floor,
    )
    assert get_universe_at(today, session) != get_universe_at(year_ago, session)
    assert get_universe_at(today, session) == frozenset({"ACME"})


def test_liquidity_floor_in_rupees_enforced(settings_floor: Settings, session: Session) -> None:
    as_of = date(2025, 6, 30)
    # exactly at floor: 50 * 1_000_000 = 5e7 == floor -> included
    at_floor = _liquid_history(50.0, 1_000_000, 300, as_of)
    below = _liquid_history(49.0, 1_000_000, 300, as_of)  # 4.9e7 < floor
    frames = {"ATFLOOR": at_floor, "BELOW": below}
    snap = build_universe_snapshot(
        as_of,
        seed=["ATFLOOR", "BELOW"],
        ohlcv_lookup=_make_lookup(frames),
        session=session,
        settings=settings_floor,
    )
    assert "ATFLOOR" in snap.members
    assert "BELOW" not in snap.members


@pytest.fixture
def settings_floor() -> Settings:
    return Settings(
        _env_file=None,
        universe_liquidity_floor_inr=50_000_000,
        universe_min_history_days=252,
    )
