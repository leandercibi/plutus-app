"""Resolve signal symbols to sectors, cached in the DB.

Sectors come from Marketaux's entity search so the strings match the taxonomy
used by its ``industries`` news filter exactly. Results are cached in
``sector_cache`` because sectors are static — a symbol is looked up once.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.data.providers.marketaux_provider import MarketauxProvider
from plutus.db.models import SectorCache

logger = logging.getLogger(__name__)


def _upsert_sector(db: Session, symbol: str, sector: str) -> None:
    row = db.get(SectorCache, symbol)
    now = datetime.utcnow()
    if row is None:
        db.add(SectorCache(symbol=symbol, sector=sector, updated_at=now))
    else:
        row.sector = sector
        row.updated_at = now


def resolve_sectors(
    db: Session, symbols: list[str], provider: MarketauxProvider
) -> dict[str, str | None]:
    """Return {symbol: sector}. Cache hits are free; misses call entity search.

    Only successful (non-None) lookups are cached, so a transient failure is
    retried on the next request rather than pinned.
    """
    if not symbols:
        return {}

    rows = db.execute(select(SectorCache).where(SectorCache.symbol.in_(symbols))).scalars().all()
    cached = {r.symbol: r.sector for r in rows}

    result: dict[str, str | None] = {}
    for sym in symbols:
        if sym in cached:
            result[sym] = cached[sym]
            continue
        sector: str | None = None
        try:
            sector = provider.resolve_industry(sym)
        except Exception:
            logger.warning("sector resolve failed for %s", sym, exc_info=True)
        result[sym] = sector
        if sector:
            _upsert_sector(db, sym, sector)

    db.flush()
    return result


def top_sectors(sector_map: dict[str, str | None], limit: int) -> list[str]:
    """Sectors ordered by how many signal symbols fall in them (desc)."""
    counts: dict[str, int] = {}
    for sector in sector_map.values():
        if sector:
            counts[sector] = counts.get(sector, 0) + 1
    ranked = sorted(counts, key=lambda s: (-counts[s], s))
    return ranked[:limit]
