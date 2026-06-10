"""
tickertape.py — Tickertape data layer (sector, MF delta, beta).

Design:
  • 24-hour disk cache per symbol per data-type.
  • Polite HTTP: 1 s delay between requests, 10 s timeout.
  • Graceful fallback: if API is down, returns None / UNKNOWN.
  • NSE symbols are passed directly to the Tickertape API (most map 1:1).
  • `SECTOR_FALLBACK` covers the 200 most common NSE stocks so sector data
    survives without any network access.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

CACHE_DIR = Path("src/plutus/data/.cache/tickertape")
CACHE_TTL_HOURS = 24
_BASE = "https://api.tickertape.in"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://tickertape.in",
    "Referer": "https://tickertape.in/",
}
_LAST_REQUEST_TS: list[float] = [0.0]
_MIN_INTERVAL_S = 1.0

# ── Sector fallback for top-200 NSE stocks ────────────────────────────────────
# Avoids ANY network calls during the weekly pipeline's critical path.
SECTOR_FALLBACK: dict[str, str] = {
    # LARGE CAP
    "RELIANCE": "ENERGY", "TCS": "IT", "INFY": "IT", "HDFCBANK": "BANK",
    "ICICIBANK": "BANK", "HINDUNILVR": "FMCG", "BAJFINANCE": "BANK",
    "BHARTIARTL": "TELECOM", "KOTAKBANK": "BANK", "LT": "INFRA",
    "AXISBANK": "BANK", "TITAN": "CONSUMER", "MARUTI": "AUTO",
    "ASIANPAINT": "CONSUMER", "HCLTECH": "IT", "WIPRO": "IT",
    "SUNPHARMA": "PHARMA", "NESTLEIND": "FMCG", "POWERGRID": "ENERGY",
    "NTPC": "ENERGY", "ONGC": "ENERGY", "COALINDIA": "ENERGY",
    "TECHM": "IT", "LTIM": "IT", "BAJAJFINSV": "BANK",
    "ADANIENT": "INFRA", "ADANIPORTS": "INFRA", "ADANIGREEN": "ENERGY",
    "ADANITRANS": "ENERGY", "JSWSTEEL": "METAL", "TATASTEEL": "METAL",
    "HINDALCO": "METAL", "VEDL": "METAL", "SAIL": "METAL",
    "TATAMOTORS": "AUTO", "M&M": "AUTO", "HEROMOTOCO": "AUTO",
    "BAJAJ-AUTO": "AUTO", "EICHERMOT": "AUTO", "TVSMOTOR": "AUTO",
    "CIPLA": "PHARMA", "DRREDDY": "PHARMA", "DIVISLAB": "PHARMA",
    "APOLLOHOSP": "PHARMA", "AUROPHARMA": "PHARMA", "BIOCON": "PHARMA",
    "IPCALAB": "PHARMA", "LUPIN": "PHARMA", "TORNTPHARM": "PHARMA",
    "GRASIM": "CONSUMER", "ULTRACEMCO": "INFRA", "ACC": "INFRA",
    "AMBUJACEM": "INFRA", "SHREECEM": "INFRA", "DALMIACM": "INFRA",
    "INDUSINDBK": "BANK", "FEDERALBNK": "BANK", "BANDHANBNK": "BANK",
    "IDFCFIRSTB": "BANK", "RBLBANK": "BANK", "PNB": "BANK",
    "BANKBARODA": "BANK", "CANBK": "BANK", "SBIN": "BANK",
    "UNIONBANK": "BANK", "INDIANB": "BANK", "IOB": "BANK",
    "LTTS": "IT", "MPHASIS": "IT", "PERSISTENT": "IT",
    "COFORGE": "IT", "NAUKRI": "IT", "ZOMATO": "CONSUMER",
    "PAYTM": "FINTECH", "POLICYBZR": "FINTECH", "DMART": "CONSUMER",
    "TRENT": "CONSUMER", "ABFRL": "CONSUMER", "RAYMOND": "CONSUMER",
    "WHIRLPOOL": "CONSUMER", "DIXON": "CONSUMER", "AMBER": "CONSUMER",
    "HAVELLS": "CONSUMER", "VOLTAS": "CONSUMER", "BLUESTARCO": "CONSUMER",
    "BPCL": "ENERGY", "HPCL": "ENERGY", "IOC": "ENERGY", "GAIL": "ENERGY",
    "IGL": "ENERGY", "MGL": "ENERGY", "PETRONET": "ENERGY",
    "NMDC": "METAL", "HINDZINC": "METAL", "NATIONALUM": "METAL",
    "JINDALSTEL": "METAL", "JSL": "METAL", "RATNAMANI": "METAL",
    "DLF": "REALTY", "GODREJPROP": "REALTY", "OBEROIRLTY": "REALTY",
    "PRESTIGE": "REALTY", "BRIGADE": "REALTY", "SOBHA": "REALTY",
    "PHOENIXLTD": "REALTY", "MAHLIFE": "REALTY",
    "SBILIFE": "INSURANCE", "HDFCLIFE": "INSURANCE", "ICICIPRULI": "INSURANCE",
    "MAXFINSERV": "INSURANCE", "STARHEALTH": "INSURANCE", "NIACL": "INSURANCE",
    "CHOLAFIN": "FINTECH", "MUTHOOTFIN": "FINTECH", "BAJAJHLDNG": "FINTECH",
    "HDFCAMC": "FINTECH", "NIPPONLIFE": "FINTECH", "CDSL": "FINTECH",
    "BSE": "FINTECH", "MCX": "FINTECH", "CAMS": "FINTECH",
    "ZYDUSLIFE": "PHARMA", "ALKEM": "PHARMA", "ABBOTINDIA": "PHARMA",
    "PFIZER": "PHARMA", "GLAXO": "PHARMA", "SANOFI": "PHARMA",
    "SIEMENS": "INFRA", "ABB": "INFRA", "BHEL": "INFRA",
    "CUMMINSIND": "INFRA", "THERMAX": "INFRA", "KEC": "INFRA",
    "KALPATPOWR": "INFRA", "IRFC": "INFRA", "RVNL": "INFRA",
    "IRCON": "INFRA", "NBCC": "INFRA", "HUDCO": "INFRA",
    "TATACOMM": "TELECOM", "VODAFONE": "TELECOM", "HFCL": "TELECOM",
    "PIIND": "PHARMA", "UPL": "PHARMA", "BAYER": "PHARMA",
    "GODREJCP": "FMCG", "DABUR": "FMCG", "BRITANNIA": "FMCG",
    "COLPAL": "FMCG", "MARICO": "FMCG", "EMAMILTD": "FMCG",
    "TATACONSUM": "FMCG", "ITC": "FMCG", "PGHH": "FMCG",
    "MCDOWELL-N": "FMCG", "UBL": "FMCG", "RADICO": "FMCG",
    "INDIGO": "AUTO", "SPICEJET": "AUTO", "GMRAIRPORT": "INFRA",
    "ZEEL": "MEDIA", "SUNTV": "MEDIA", "NETWORK18": "MEDIA",
    "PVR": "MEDIA", "INOXLEISUR": "MEDIA",
    "JUBLFOOD": "CONSUMER", "WESTLIFE": "CONSUMER",
    "CONCOR": "INFRA", "GATEWAY": "INFRA",
    "ASHOKLEY": "AUTO", "ESCORTS": "AUTO", "FORCE": "AUTO",
    "DEEPAKNTR": "PHARMA", "AAPL": "IT",
}


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_path(symbol: str, dtype: str) -> Path:
    return CACHE_DIR / dtype / f"{symbol.upper()}.json"


def _read_cache(symbol: str, dtype: str) -> Optional[dict]:
    p = _cache_path(symbol, dtype)
    if not p.exists():
        return None
    age_h = (time.time() - p.stat().st_mtime) / 3600
    if age_h > CACHE_TTL_HOURS:
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _write_cache(symbol: str, dtype: str, data: dict) -> None:
    p = _cache_path(symbol, dtype)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def _get(path: str) -> Optional[dict]:
    """Polite GET with rate-limiting and timeout."""
    elapsed = time.monotonic() - _LAST_REQUEST_TS[0]
    if elapsed < _MIN_INTERVAL_S:
        time.sleep(_MIN_INTERVAL_S - elapsed)
    try:
        resp = requests.get(f"{_BASE}{path}", headers=_HEADERS, timeout=10)
        _LAST_REQUEST_TS[0] = time.monotonic()
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def get_sector(symbol: str) -> Optional[str]:
    """
    Return sector string for an NSE symbol.
    Order: disk-cache → SECTOR_FALLBACK → Tickertape API → None.
    """
    sym = symbol.upper()

    cached = _read_cache(sym, "sector")
    if cached:
        return cached.get("sector")

    # Static fallback covers 200 most-common stocks
    if sym in SECTOR_FALLBACK:
        sector = SECTOR_FALLBACK[sym]
        _write_cache(sym, "sector", {"sector": sector, "source": "fallback"})
        return sector

    # Live API
    data = _get(f"/stocks/{sym}/info")
    if data:
        sector = (
            data.get("sector")
            or data.get("data", {}).get("sector")
            or None
        )
        if sector:
            _write_cache(sym, "sector", {"sector": sector, "source": "api"})
            return sector

    return None


def get_beta(symbol: str) -> Optional[float]:
    """
    Return 1-year beta vs Nifty 50.
    Computed locally from OHLCV if Tickertape API is unavailable.
    """
    sym = symbol.upper()

    cached = _read_cache(sym, "beta")
    if cached:
        return cached.get("beta")

    # Try Tickertape API first
    data = _get(f"/stocks/{sym}/ratios")
    if data:
        beta_raw = (
            data.get("beta")
            or data.get("data", {}).get("beta")
        )
        if beta_raw is not None:
            beta = float(beta_raw)
            _write_cache(sym, "beta", {"beta": beta, "source": "api"})
            return beta

    # Local computation from OHLCV
    return _compute_beta_locally(sym)


def _compute_beta_locally(symbol: str) -> Optional[float]:
    """Compute 1Y beta vs Nifty 50 from local OHLCV. Cached on success."""
    try:
        from plutus.data.ohlcv import fetch_ohlcv
        import numpy as np

        df_stock = fetch_ohlcv(symbol, days=260, interval="1d")
        df_nifty = fetch_ohlcv("^NSEI", days=260, interval="1d", exchange="INDEX")
        if df_stock is None or df_nifty is None or len(df_stock) < 60:
            return None

        stock_ret = df_stock["Close"].pct_change().dropna()
        nifty_ret = df_nifty["Close"].pct_change().dropna()
        aligned = stock_ret.align(nifty_ret, join="inner")
        s, n = aligned
        if len(s) < 30:
            return None
        cov   = float(np.cov(s, n)[0][1])
        var_n = float(np.var(n))
        if var_n == 0:
            return None
        beta = round(cov / var_n, 3)
        _write_cache(symbol, "beta", {"beta": beta, "source": "local_ohlcv"})
        return beta
    except Exception:
        return None


def get_mf_holdings_delta(symbol: str) -> dict:
    """
    Return MF accumulation signal.
    {
      "verdict": "ACCUMULATING" | "REDUCING" | "NEUTRAL" | "UNKNOWN",
      "change_pct": float | None,   # quarter-over-quarter % change in MF holding
      "mf_count": int,              # number of mutual funds holding the stock
    }
    Cached 24h. Falls back to UNKNOWN on any error.
    """
    sym = symbol.upper()

    cached = _read_cache(sym, "mf_delta")
    if cached:
        return cached

    data = _get(f"/stocks/{sym}/holders")
    if data:
        result = _parse_mf_holdings(data)
        _write_cache(sym, "mf_delta", result)
        return result

    return {"verdict": "UNKNOWN", "change_pct": None, "mf_count": 0}


def _parse_mf_holdings(raw: dict) -> dict:
    """Extract MF delta from Tickertape holders response."""
    try:
        holders = raw.get("data") or raw
        if isinstance(holders, list):
            mf_entries = [h for h in holders if "mutual" in str(h.get("type", "")).lower()]
        elif isinstance(holders, dict):
            mf_entries = holders.get("mutualFund", []) or holders.get("mf", [])
        else:
            mf_entries = []

        mf_count = len(mf_entries)
        # Try to compute QoQ change
        changes = []
        for entry in mf_entries:
            curr = entry.get("currentHolding") or entry.get("current")
            prev = entry.get("previousHolding") or entry.get("previous")
            if curr is not None and prev is not None and prev != 0:
                changes.append((float(curr) - float(prev)) / abs(float(prev)) * 100)

        if changes:
            avg_change = sum(changes) / len(changes)
            verdict = (
                "ACCUMULATING" if avg_change > 2.0
                else "REDUCING" if avg_change < -2.0
                else "NEUTRAL"
            )
            return {"verdict": verdict, "change_pct": round(avg_change, 2), "mf_count": mf_count}
    except Exception:
        pass

    return {"verdict": "UNKNOWN", "change_pct": None, "mf_count": 0}


def invalidate_cache(symbol: str) -> None:
    """Remove all cached data for a symbol (forces refresh on next call)."""
    sym = symbol.upper()
    for dtype in ("sector", "beta", "mf_delta"):
        p = _cache_path(sym, dtype)
        if p.exists():
            p.unlink()
