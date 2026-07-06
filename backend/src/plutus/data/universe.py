from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.config.settings import Settings, get_settings
from plutus.db.models import Universe

logger = logging.getLogger(__name__)

_LIQUIDITY_WINDOW = 20

OHLCVLookup = Callable[[str, date], pd.DataFrame]


@dataclass(frozen=True)
class UniverseSnapshot:
    as_of_date: date
    members: frozenset[str]
    rejected_for_liquidity: frozenset[str]


def _median_traded_value(candles: pd.DataFrame) -> Decimal:
    window = candles.tail(_LIQUIDITY_WINDOW)
    traded_value = window["close"].astype(float) * window["volume"].astype(float)
    return Decimal(str(float(traded_value.median())))


def build_universe_snapshot(
    as_of: date,
    seed: list[str],
    ohlcv_lookup: OHLCVLookup,
    session: Session,
    settings: Settings | None = None,
) -> UniverseSnapshot:
    """Build a deterministic PIT universe snapshot and persist it (A17).

    Membership: >= min_history_days of OHLCV AND 20d median traded value (close*volume)
    >= liquidity_floor_inr. Persists one row per (symbol, as_of_date).
    """
    cfg = settings or get_settings()
    members: set[str] = set()
    rejected: set[str] = set()

    for symbol in seed:
        candles = ohlcv_lookup(symbol, as_of)
        if candles is None or candles.empty:
            rejected.add(symbol)
            in_universe = False
            mtv = Decimal("0")
        elif len(candles) < cfg.universe_min_history_days:
            rejected.add(symbol)
            in_universe = False
            mtv = _median_traded_value(candles)
        else:
            mtv = _median_traded_value(candles)
            in_universe = mtv >= Decimal(cfg.universe_liquidity_floor_inr)
            if in_universe:
                members.add(symbol)
            else:
                rejected.add(symbol)

        _upsert_row(session, symbol, as_of, mtv, in_universe)

    session.commit()
    return UniverseSnapshot(
        as_of_date=as_of,
        members=frozenset(members),
        rejected_for_liquidity=frozenset(rejected),
    )


def _upsert_row(
    session: Session, symbol: str, as_of: date, mtv: Decimal, in_universe: bool
) -> None:
    existing = (
        session.execute(
            select(Universe).where(Universe.symbol == symbol, Universe.as_of_date == as_of)
        )
        .scalars()
        .first()
    )
    if existing is not None:
        existing.median_traded_value_inr = mtv
        existing.in_universe = in_universe
    else:
        session.add(
            Universe(
                symbol=symbol,
                as_of_date=as_of,
                median_traded_value_inr=mtv,
                in_universe=in_universe,
            )
        )


def get_universe_at(as_of: date, session: Session) -> frozenset[str]:
    """Look up the persisted PIT snapshot. Never recomputes (A17)."""
    rows = (
        session.execute(
            select(Universe.symbol).where(
                Universe.as_of_date == as_of, Universe.in_universe.is_(True)
            )
        )
        .scalars()
        .all()
    )
    return frozenset(rows)


def get_live_universe(
    seed: list[str], ohlcv_lookup: OHLCVLookup, session: Session
) -> UniverseSnapshot:
    """Live (today) universe build. NOT for backtests — those use get_universe_at."""
    return build_universe_snapshot(date.today(), seed, ohlcv_lookup, session)
