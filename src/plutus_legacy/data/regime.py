# src/plutus/data/regime.py
"""
Nifty regime detection and sector relative-strength computation.

Public API:
    fetch_index_ohlcv(symbol, days) -> DataFrame
    get_nifty_regime(force=False) -> dict
    get_sector_strength(force=False) -> dict[str, float]
    persist_regime_snapshot(db_session) -> MarketRegimeSnapshot
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Index symbol map (internal name → yfinance ticker) ───────────────────

INDEX_YF_MAP: dict[str, str] = {
    "NIFTY_50": "^NSEI",
    "NIFTY_BANK": "^NSEBANK",
    "NIFTY_IT": "^CNXIT",
    "NIFTY_AUTO": "^CNXAUTO",
    "NIFTY_FMCG": "^CNXFMCG",
    "NIFTY_PHARMA": "^CNXPHARMA",
    "NIFTY_METAL": "^CNXMETAL",
    "NIFTY_REALTY": "^CNXREALTY",
    "NIFTY_ENERGY": "^CNXENERGY",
    "NIFTY_INFRA": "^CNXINFRA",
    "NIFTY_PSE": "^CNXPSE",
    "NIFTY_MEDIA": "^CNXMEDIA",
}

# Human-readable short names for dashboard / scoring
SECTOR_DISPLAY: dict[str, str] = {
    "NIFTY_BANK": "BANK",
    "NIFTY_IT": "IT",
    "NIFTY_AUTO": "AUTO",
    "NIFTY_FMCG": "FMCG",
    "NIFTY_PHARMA": "PHARMA",
    "NIFTY_METAL": "METAL",
    "NIFTY_REALTY": "REALTY",
    "NIFTY_ENERGY": "ENERGY",
    "NIFTY_INFRA": "INFRA",
    "NIFTY_PSE": "PSE",
    "NIFTY_MEDIA": "MEDIA",
}

# ── Disk cache ────────────────────────────────────────────────────────────

_REGIME_CACHE_DIR = Path("src/plutus/data/.cache/regime")
_REGIME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_REGIME_CACHE_FILE = _REGIME_CACHE_DIR / "regime_snapshot.json"
_SECTOR_CACHE_FILE = _REGIME_CACHE_DIR / "sector_strength.json"
_CACHE_TTL_DAYS = 7

_regime_cache: Optional[dict] = None
_sector_cache: Optional[dict] = None


def _cache_valid(path: Path) -> bool:
    if not path.exists():
        return False
    age_days = (datetime.utcnow().timestamp() - path.stat().st_mtime) / 86400
    return age_days < _CACHE_TTL_DAYS


def _load_json_cache(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _write_json_cache(path: Path, data: dict) -> None:
    try:
        path.write_text(json.dumps(data))
    except Exception as e:
        logger.debug("cache write failed %s: %s", path, e)


# ── Fetch ─────────────────────────────────────────────────────────────────


def fetch_index_ohlcv(symbol: str, days: int = 90) -> pd.DataFrame:
    """Fetch OHLCV for a Nifty index using yfinance (indices are not on jugaad).

    `symbol` should be one of INDEX_YF_MAP keys, e.g. "NIFTY_50".
    Falls back to the raw yfinance ticker if symbol is not in the map.
    """
    from plutus.data.ohlcv import fetch_ohlcv

    yf_ticker = INDEX_YF_MAP.get(symbol, symbol)
    # Indices live on yfinance only; bypass jugaad by passing exchange="INDEX"
    df = fetch_ohlcv(yf_ticker, days=days, interval="1d", exchange="INDEX")
    return df


# ── EMA helpers ───────────────────────────────────────────────────────────


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


# ── get_nifty_regime ──────────────────────────────────────────────────────


def get_nifty_regime(force: bool = False) -> dict:
    """Return {trend, slope, distance_from_ema50_pct} for the current Nifty50 regime.

    Caches to disk for 7 days; use force=True to bypass cache.

    Rules:
      BULL  — Close > EMA50 AND 5-day EMA50 slope > 0
      BEAR  — Close < EMA50 AND 5-day EMA50 slope < 0
      SIDEWAYS — everything else
    """
    global _regime_cache

    if not force and _regime_cache is not None:
        return _regime_cache

    if not force and _cache_valid(_REGIME_CACHE_FILE):
        cached = _load_json_cache(_REGIME_CACHE_FILE)
        if cached:
            _regime_cache = cached
            return _regime_cache

    df = fetch_index_ohlcv("NIFTY_50", days=120)
    ema50 = _ema(df["Close"], 50)

    close_today = float(df["Close"].iloc[-1])
    ema50_today = float(ema50.iloc[-1])
    ema50_5d_ago = float(ema50.iloc[-6]) if len(ema50) >= 6 else ema50_today

    slope = (ema50_today - ema50_5d_ago) / ema50_5d_ago if ema50_5d_ago != 0 else 0.0
    distance_pct = (
        (close_today - ema50_today) / ema50_today * 100 if ema50_today != 0 else 0.0
    )

    if close_today > ema50_today and slope > 0:
        trend = "BULL"
    elif close_today < ema50_today and slope < 0:
        trend = "BEAR"
    else:
        trend = "SIDEWAYS"

    result = {
        "trend": trend,
        "slope": round(slope, 6),
        "distance_from_ema50_pct": round(distance_pct, 2),
    }

    _regime_cache = result
    _write_json_cache(_REGIME_CACHE_FILE, result)
    logger.info("regime computed: %s", result)
    return result


# ── get_sector_strength ───────────────────────────────────────────────────


def get_sector_strength(force: bool = False) -> dict[str, float]:
    """Return RS of each sector vs Nifty50 over the last 30 trading days.

    RS = (1 + sector_30d_return) / (1 + nifty_30d_return)
    Values > 1 → sector outperforming; < 1 → underperforming.

    Result keys use SECTOR_DISPLAY short names (e.g. "IT", "BANK").
    """
    global _sector_cache

    if not force and _sector_cache is not None:
        return _sector_cache

    if not force and _cache_valid(_SECTOR_CACHE_FILE):
        cached = _load_json_cache(_SECTOR_CACHE_FILE)
        if cached:
            _sector_cache = cached
            return _sector_cache

    nifty_df = fetch_index_ohlcv("NIFTY_50", days=60)
    nifty_close = nifty_df["Close"]
    if len(nifty_close) < 31:
        logger.warning(
            "Nifty has only %d bars — sector RS unreliable", len(nifty_close)
        )
        nifty_30d = float(nifty_close.iloc[-1] / nifty_close.iloc[0]) - 1
    else:
        nifty_30d = float(nifty_close.iloc[-1] / nifty_close.iloc[-31]) - 1

    rs: dict[str, float] = {}
    for internal_name, display_name in SECTOR_DISPLAY.items():
        try:
            df = fetch_index_ohlcv(internal_name, days=60)
            close = df["Close"]
            if len(close) < 31:
                sector_30d = float(close.iloc[-1] / close.iloc[0]) - 1
            else:
                sector_30d = float(close.iloc[-1] / close.iloc[-31]) - 1
            rs[display_name] = round((1 + sector_30d) / (1 + nifty_30d), 4)
        except Exception as e:
            logger.warning("sector RS failed for %s: %s", internal_name, e)

    _sector_cache = rs
    _write_json_cache(_SECTOR_CACHE_FILE, rs)
    logger.info("sector_strength: %s", rs)
    return rs


# ── Persistence ───────────────────────────────────────────────────────────


def persist_regime_snapshot(db_session, snapshot_date: Optional[date] = None):
    """Compute regime + sector strength and persist to market_regime_snapshots.

    Upserts on snapshot_date (no duplicate rows per day).
    Returns the ORM row.
    """
    from plutus.db.models import MarketRegimeSnapshot

    today = snapshot_date or date.today()

    regime = get_nifty_regime(force=True)
    sector_rs = get_sector_strength(force=True)

    existing = (
        db_session.query(MarketRegimeSnapshot).filter_by(snapshot_date=today).first()
    )
    if existing:
        existing.nifty_trend = regime["trend"]
        existing.nifty_slope = regime["slope"]
        existing.distance_from_ema50_pct = regime["distance_from_ema50_pct"]
        existing.sector_rs = sector_rs
        row = existing
    else:
        row = MarketRegimeSnapshot(
            snapshot_date=today,
            nifty_trend=regime["trend"],
            nifty_slope=regime["slope"],
            distance_from_ema50_pct=regime["distance_from_ema50_pct"],
            sector_rs=sector_rs,
        )
        db_session.add(row)

    db_session.commit()
    return row
