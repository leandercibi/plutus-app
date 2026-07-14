from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# 30 liquid Nifty 50 symbols (NS suffix for NSE)
_SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "HINDUNILVR.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
    "KOTAKBANK.NS",
    "LT.NS",
    "AXISBANK.NS",
    "ASIANPAINT.NS",
    "MARUTI.NS",
    "BAJFINANCE.NS",
    "TITAN.NS",
    "HCLTECH.NS",
    "SUNPHARMA.NS",
    "WIPRO.NS",
    "ULTRACEMCO.NS",
    "NESTLEIND.NS",
    "TECHM.NS",
    "BAJAJFINSV.NS",
    "NTPC.NS",
    "POWERGRID.NS",
    "ONGC.NS",
    "COALINDIA.NS",
    "JSWSTEEL.NS",
    "HEROMOTOCO.NS",
    "ADANIENT.NS",
]

_CACHE_DIR = Path("cache/regime")
_CACHE_TTL_HOURS = 6


def _cache_path(key: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"breadth_{key}.parquet"


def _load_cache(key: str) -> pd.DataFrame | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    age_hours = (
        pd.Timestamp.now() - pd.Timestamp(p.stat().st_mtime, unit="s")
    ).total_seconds() / 3600
    if age_hours > _CACHE_TTL_HOURS:
        return None
    return pd.read_parquet(p)


def _save_cache(key: str, df: pd.DataFrame) -> None:
    df.to_parquet(_cache_path(key))


def _fetch_closes(start: date, end: date) -> pd.DataFrame:
    key = f"{start}_{end}"
    cached = _load_cache(key)
    if cached is not None:
        return cached
    extra = timedelta(days=250)  # need history for 200d DMA
    fetch_start = start - extra
    try:
        raw = yf.download(
            _SYMBOLS,
            start=fetch_start,
            end=end + timedelta(days=1),
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
        if raw.empty:
            raise ValueError("empty download")
        # extract Close for each symbol
        if isinstance(raw.columns, pd.MultiIndex):
            closes = pd.concat(
                {sym.replace(".NS", ""): raw[sym]["Close"] for sym in _SYMBOLS if sym in raw},
                axis=1,
            )
        else:
            closes = raw[["Close"]].rename(columns={"Close": _SYMBOLS[0].replace(".NS", "")})
        closes.index = pd.to_datetime(closes.index).normalize()
        closes = closes.sort_index().dropna(how="all")
        _save_cache(key, closes)
        return cast(pd.DataFrame, closes)
    except Exception as exc:
        logger.warning("breadth fetch failed: %s", exc)
        return pd.DataFrame()


class BreadthYFinanceProvider:
    def fetch_pct_above_dma(self, window: int, start: date, end: date) -> pd.Series:
        closes = _fetch_closes(start, end)
        if closes.empty:
            idx = pd.date_range(start, end, freq="B")
            return pd.Series(0.5, index=idx)
        dma = closes.rolling(window, min_periods=window // 2).mean()
        above = (closes > dma).astype(float)
        result = above.mean(axis=1)
        return result.loc[str(start) : str(end)].clip(0.0, 1.0)  # type: ignore[misc]

    def fetch_advance_decline(self, start: date, end: date) -> pd.Series:
        closes = _fetch_closes(start, end)
        if closes.empty:
            idx = pd.date_range(start, end, freq="B")
            return pd.Series(1.0, index=idx)
        daily_ret = closes.pct_change()
        adv = (daily_ret > 0).sum(axis=1)
        dec = (daily_ret < 0).sum(axis=1)
        ratio = adv / dec.replace(0, np.nan)
        return ratio.fillna(1.0).loc[str(start) : str(end)]  # type: ignore[misc]
