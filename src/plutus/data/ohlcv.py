# src/plutus/data/ohlcv.py
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from plutus.config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = Path("src/plutus/data/.cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OHLCV_CACHE_TTL_HOURS = 12


def _nse_symbol(symbol: str, exchange: str = "NSE") -> str:
    suffix = ".NS" if exchange == "NSE" else ".BO"
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}{suffix}"


def _bare_symbol(symbol: str) -> str:
    for suffix in (".NS", ".BO"):
        if symbol.endswith(suffix):
            return symbol[: -len(suffix)]
    return symbol


def _cache_path(symbol: str, days: int) -> Path:
    return CACHE_DIR / f"ohlcv_{symbol.upper()}_{days}.parquet"


def _read_cache(symbol: str, days: int) -> pd.DataFrame | None:
    p = _cache_path(symbol, days)
    if not p.exists():
        return None
    age_h = (datetime.utcnow().timestamp() - p.stat().st_mtime) / 3600
    if age_h > OHLCV_CACHE_TTL_HOURS:
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


def _write_cache(symbol: str, days: int, df: pd.DataFrame) -> None:
    try:
        df.to_parquet(_cache_path(symbol, days))
    except Exception as e:
        logger.debug("Parquet cache write failed for %s: %s", symbol, e)


# ── jugaad-data (primary for daily OHLCV) ────────────────────────────────

def _fetch_jugaad(symbol: str, days: int) -> pd.DataFrame:
    """Fetch daily OHLCV from NSE via jugaad-data. Direct from exchange, no API key."""
    from jugaad_data.nse import stock_df

    bare = _bare_symbol(symbol)
    end_date = date.today()
    start_date = end_date - timedelta(days=days + 10)

    raw = stock_df(symbol=bare, from_date=start_date, to_date=end_date, series="EQ")
    if raw.empty:
        raise ValueError(f"jugaad-data returned no data for {bare}")

    df = pd.DataFrame({
        "Open": raw["OPEN"].values,
        "High": raw["HIGH"].values,
        "Low": raw["LOW"].values,
        "Close": raw["CLOSE"].values,
        "Volume": raw["VOLUME"].values,
    }, index=pd.to_datetime(raw["DATE"]).dt.tz_localize(None))

    df = df.sort_index().dropna()
    return df.tail(days)


# ── yfinance (fallback) ──────────────────────────────────────────────────

def _fetch_yfinance(symbol: str, days: int, interval: str, exchange: str) -> pd.DataFrame:
    ticker_sym = _nse_symbol(symbol, exchange)
    end = datetime.now()
    start = end - timedelta(days=days + 10)
    df = yf.download(
        ticker_sym,
        start=start,
        end=end,
        interval=interval,
        progress=False,
        auto_adjust=True,
    )
    if df.empty:
        raise ValueError(f"yfinance returned no data for {ticker_sym}")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df.tail(days)


# ── Public API ───────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def fetch_ohlcv(
    symbol: str,
    days: int = 90,
    interval: str = "1d",
    exchange: str = "NSE",
) -> pd.DataFrame:
    """
    Returns DataFrame with columns: Open, High, Low, Close, Volume.
    Index: DatetimeIndex (timezone-naive).

    Daily-interval calls are disk-cached as Parquet for 12h.
    Primary source: jugaad-data (direct NSE). Fallback: yfinance.
    """
    if interval == "1d":
        cached = _read_cache(symbol, days)
        if cached is not None:
            return cached

    df = None

    # jugaad-data only supports daily interval and NSE
    if interval == "1d" and exchange == "NSE":
        try:
            df = _fetch_jugaad(symbol, days)
            logger.info("OHLCV for %s via jugaad-data (%d rows)", symbol, len(df))
        except Exception as e:
            logger.warning("jugaad-data failed for %s: %s — falling back to yfinance", symbol, e)

    if df is None:
        df = _fetch_yfinance(symbol, days, interval, exchange)
        logger.info("OHLCV for %s via yfinance (%d rows)", symbol, len(df))

    if interval == "1d":
        _write_cache(symbol, days, df)
    return df


def fetch_live_price(symbol: str, exchange: str = "NSE") -> float:
    """Returns current market price (or last close). Tries jugaad-data first, then yfinance."""
    # jugaad-data live quotes (NSE only, works from Indian IPs)
    if exchange == "NSE":
        try:
            from jugaad_data.nse import NSELive
            n = NSELive()
            q = n.stock_quote(_bare_symbol(symbol))
            price = q["priceInfo"]["lastPrice"]
            if price and price > 0:
                return float(price)
        except Exception:
            pass

    # yfinance fallback
    ticker = yf.Ticker(_nse_symbol(symbol, exchange))
    info = ticker.fast_info
    price = info.last_price or info.previous_close
    if price and price > 0:
        return float(price)
    hist = ticker.history(period="1d")
    if not hist.empty:
        return float(hist["Close"].iloc[-1])

    # last resort: use cached daily data
    try:
        df = _read_cache(_bare_symbol(symbol), 90)
        if df is not None and not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass

    raise ValueError(f"No price data for {symbol}")


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds all technical indicators using pandas-ta.
    Called by strategy bundles and the technical agent.
    Returns the same DataFrame with additional columns.
    """
    import pandas_ta_classic as ta  # the maintained PyPI fork

    df.ta.ema(length=9, append=True)
    df.ta.ema(length=21, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df.ta.bbands(length=20, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.stoch(append=True)
    df.ta.adx(append=True)
    df.ta.obv(append=True)

    df["Volume_MA20"] = df["Volume"].rolling(20).mean()
    df["Volume_Ratio"] = df["Volume"] / df["Volume_MA20"]

    df["Body_Size"] = abs(df["Close"] - df["Open"])
    df["Upper_Wick"] = df["High"] - df[["Open", "Close"]].max(axis=1)
    df["Lower_Wick"] = df[["Open", "Close"]].min(axis=1) - df["Low"]

    return df.dropna(subset=["EMA_9", "RSI_14"])
