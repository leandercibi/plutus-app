# src/plutus/data/universe.py
import json
import logging
import csv
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Set

import requests

from plutus.config import settings
from plutus.data.ohlcv import fetch_ohlcv

logger = logging.getLogger(__name__)

CACHE_DIR = Path("src/plutus/data/.cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

NSE_FNO_BAN_URL = (
    "https://www.nseindia.com/api/liveEquity-derivatives"
    "?index=fno_ban_list_active"
)
FNO_BAN_FILE = Path("src/plutus/data/fno_ban_list.txt")
FNO_BAN_TTL_HOURS = 24


# ── Seed CSV ────────────────────────────────────────────────────────────────

def _load_seed_symbols(csv_path: str | None = None) -> List[str]:
    path = Path(csv_path or settings.UNIVERSE_SEED_CSV)
    if not path.exists():
        raise FileNotFoundError(
            f"Seed universe CSV missing at {path}. "
            "Populate it from NSE Nifty 500 + MidCap 150 CSVs."
        )
    symbols: List[str] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = (row.get("symbol") or "").strip().upper()
            if sym:
                symbols.append(sym)
    # de-dupe but preserve order
    return list(dict.fromkeys(symbols))


# ── F&O ban list ────────────────────────────────────────────────────

def _load_fno_ban_list() -> Set[str]:
    """Refresh ban list from NSE if local file is stale; fall back to stale on error."""
    needs_refresh = (
        not FNO_BAN_FILE.exists()
        or (datetime.utcnow().timestamp() - FNO_BAN_FILE.stat().st_mtime)
        > FNO_BAN_TTL_HOURS * 3600
    )
    if needs_refresh:
        try:
            resp = requests.get(
                NSE_FNO_BAN_URL,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                    "Referer": "https://www.nseindia.com/",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            symbols = sorted({(d.get("symbol") or "").strip().upper() for d in data if d.get("symbol")})
            FNO_BAN_FILE.parent.mkdir(parents=True, exist_ok=True)
            FNO_BAN_FILE.write_text("\n".join(symbols) + "\n")
        except Exception as e:
            logger.warning("F&O ban list refresh failed (%s); using stale file", e)

    if not FNO_BAN_FILE.exists():
        return set()
    return {
        line.strip().upper()
        for line in FNO_BAN_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }


# ── Weekly cache ────────────────────────────────────────────────────────────

def _week_tag(d: date | None = None) -> str:
    d = d or date.today()
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}W{iso_week:02d}"


def _cache_path() -> Path:
    return CACHE_DIR / f"universe_{_week_tag()}.json"


def _load_cached_universe() -> List[str] | None:
    p = _cache_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get("symbols")
    except Exception:
        return None


def _save_cached_universe(symbols: List[str]) -> None:
    _cache_path().write_text(
        json.dumps({"week": _week_tag(), "symbols": symbols}, indent=2)
    )


# ── Public API ──────────────────────────────────────────────────────────────

def get_universe(use_cache: bool = True, seed_csv: str | None = None) -> List[str]:
    """Return the filtered tradeable universe for the current ISO week."""
    if use_cache and seed_csv is None:
        cached = _load_cached_universe()
        if cached is not None:
            return cached

    seed = _load_seed_symbols(seed_csv)
    banned = _load_fno_ban_list()

    kept: List[str] = []
    for symbol in seed:
        if symbol in banned:
            continue
        try:
            df = fetch_ohlcv(symbol, days=90, interval="1d")
        except Exception as e:
            logger.debug("OHLCV fetch failed for %s: %s", symbol, e)
            continue
        if df is None or df.empty or len(df) < 30:
            continue

        last_close = float(df["Close"].iloc[-1])
        avg_volume_30d = float(df["Volume"].tail(30).mean())
        avg_value_30d_cr = float((df["Close"] * df["Volume"]).tail(30).mean()) / 1e7

        if not (settings.UNIVERSE_PRICE_MIN <= last_close <= settings.UNIVERSE_PRICE_MAX):
            continue
        if avg_volume_30d < settings.UNIVERSE_MIN_AVG_VOLUME:
            continue
        if avg_value_30d_cr < settings.UNIVERSE_MIN_AVG_VALUE_CR:
            continue

        kept.append(symbol)

    _save_cached_universe(kept)
    logger.info(
        "Universe built: %d / %d seed symbols passed filters (week %s)",
        len(kept), len(seed), _week_tag(),
    )
    return kept


def get_watchlist_symbols() -> List[str]:
    from plutus.db.session import SessionLocal
    from plutus.db.models import Watchlist
    with SessionLocal() as db:
        return [w.symbol for w in db.query(Watchlist).all()]


def get_full_analysis_set() -> List[str]:
    """Universe ∪ watchlist — watchlist symbols always pass through."""
    return list(dict.fromkeys(get_universe() + get_watchlist_symbols()))


def get_symbol_sector(symbol: str) -> str | None:
    """
    Return sector for a symbol.
    Order: Tickertape cache → SECTOR_FALLBACK → None.
    Never blocks the weekly pipeline — returns None on any failure.
    """
    try:
        from plutus.data.tickertape import get_sector as _tt_sector
        return _tt_sector(symbol)
    except Exception:
        return None
