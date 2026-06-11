# src/plutus/data/ohlcv.py
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from plutus.config import settings

logger = logging.getLogger(__name__)


# ── Angel One SmartAPI ────────────────────────────────────────────────────

_ANGEL_TOKEN_CACHE: dict = {}  # symbol -> token, loaded once per process
_ANGEL_SESSION_CACHE: dict = {}  # holds {obj, jwt} to avoid re-login
_ANGEL_RATE_LOCK = __import__("threading").Lock()
_ANGEL_LAST_CALL = [0.0]  # last call timestamp
_ANGEL_MIN_INTERVAL = 0.4  # 2.5 req/sec (safely under 3/sec limit)
# Per-minute sliding window for getCandleData (limit: 180/min)
_ANGEL_MINUTE_WINDOW: list = []  # timestamps of recent calls
_ANGEL_MINUTE_LIMIT = 170  # leave 10-call buffer under 180/min


def _angel_symbol_token(symbol: str) -> str | None:
    """Resolve NSE symbol name to Angel One instrument token."""
    global _ANGEL_TOKEN_CACHE
    if not _ANGEL_TOKEN_CACHE:
        try:
            resp = requests.get(
                "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json",
                timeout=15,
            )
            instruments = resp.json()
            _ANGEL_TOKEN_CACHE = {
                i["symbol"].upper().replace("-EQ", ""): i["token"]
                for i in instruments
                if i.get("exch_seg") == "NSE" and i.get("symbol", "").endswith("-EQ")
            }
        except Exception as e:
            logger.warning("angel_instrument_list_failed: %s", e)
            return None
    return _ANGEL_TOKEN_CACHE.get(symbol.upper())


def _angel_session():
    """Return a logged-in SmartConnect object, reusing cached session."""
    if _ANGEL_SESSION_CACHE.get("obj"):
        return _ANGEL_SESSION_CACHE["obj"]
    import pyotp
    from SmartApi import SmartConnect

    obj = SmartConnect(api_key=settings.ANGEL_API_KEY)
    totp = pyotp.TOTP(settings.ANGEL_TOTP_SECRET).now()
    obj.generateSession(settings.ANGEL_CLIENT_ID, settings.ANGEL_PASSWORD, totp)
    _ANGEL_SESSION_CACHE["obj"] = obj
    return obj


def _fetch_angelone(symbol: str, days: int) -> pd.DataFrame:
    """Fetch daily OHLCV from Angel One SmartAPI (max 3 req/sec)."""
    import time

    token = _angel_symbol_token(_bare_symbol(symbol))
    if not token:
        raise ValueError(f"No Angel One token for {symbol}")
    obj = _angel_session()
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days + 10)
    params = {
        "exchange": "NSE",
        "symboltoken": token,
        "interval": "ONE_DAY",
        "fromdate": start_dt.strftime("%Y-%m-%d 09:00"),
        "todate": end_dt.strftime("%Y-%m-%d 15:30"),
    }
    with _ANGEL_RATE_LOCK:
        now = time.time()
        # Enforce per-second limit
        elapsed = now - _ANGEL_LAST_CALL[0]
        if elapsed < _ANGEL_MIN_INTERVAL:
            time.sleep(_ANGEL_MIN_INTERVAL - elapsed)
        # Enforce per-minute limit (180/min)
        now = time.time()
        _ANGEL_MINUTE_WINDOW[:] = [t for t in _ANGEL_MINUTE_WINDOW if now - t < 60]
        if len(_ANGEL_MINUTE_WINDOW) >= _ANGEL_MINUTE_LIMIT:
            sleep_for = 60 - (now - _ANGEL_MINUTE_WINDOW[0])
            if sleep_for > 0:
                logger.info("angel_rate_limit_minute: sleeping %.1fs", sleep_for)
                time.sleep(sleep_for)
        _ANGEL_MINUTE_WINDOW.append(time.time())
        _ANGEL_LAST_CALL[0] = time.time()
    data = obj.getCandleData(params)
    if not data.get("data"):
        raise ValueError(f"Angel One returned no data for {symbol}")
    df = pd.DataFrame(
        data["data"], columns=["timestamp", "Open", "High", "Low", "Close", "Volume"]
    )
    df.index = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df = df[~df.index.duplicated(keep="last")]
    return df.tail(days)


class InsufficientDataError(ValueError):
    """Raised when fetched bars fall below the minimum required for backtesting."""

    def __init__(self, bars_fetched: int, bars_required: int, symbol: str):
        self.bars_fetched = bars_fetched
        self.bars_required = bars_required
        self.symbol = symbol
        super().__init__(
            f"Only {bars_fetched} bars retrieved for {symbol}, need {bars_required}"
        )


CACHE_DIR = Path("src/plutus/data/.cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OHLCV_CACHE_TTL_HOURS = 12


def _nse_symbol(symbol: str, exchange: str = "NSE") -> str:
    # Index tickers (e.g. ^NSEI) are passed through as-is
    if symbol.startswith("^"):
        return symbol
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
    import time as _time

    age_h = (_time.time() - p.stat().st_mtime) / 3600
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
    import concurrent.futures
    from jugaad_data.nse import stock_df

    bare = _bare_symbol(symbol)
    end_date = date.today()
    start_date = end_date - timedelta(days=days + 10)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(
            stock_df, symbol=bare, from_date=start_date, to_date=end_date, series="EQ"
        )
        try:
            raw = future.result(timeout=15)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"jugaad-data timed out for {bare}")
    if raw.empty:
        raise ValueError(f"jugaad-data returned no data for {bare}")

    df = pd.DataFrame(
        {
            "Open": raw["OPEN"].values,
            "High": raw["HIGH"].values,
            "Low": raw["LOW"].values,
            "Close": raw["CLOSE"].values,
            "Volume": raw["VOLUME"].values,
        },
        index=pd.to_datetime(raw["DATE"]).dt.tz_localize(None),
    )

    df = df.sort_index().dropna()
    df = df[~df.index.duplicated(keep="last")]
    return df.tail(days)


# ── yfinance (fallback) ──────────────────────────────────────────────────

_YF_TIMEOUT = 15  # seconds per request


def _fetch_yfinance(
    symbol: str, days: int, interval: str, exchange: str
) -> pd.DataFrame:
    ticker_sym = _nse_symbol(symbol, exchange)
    # For index tickers (^NSEI, ^NSEBANK, etc.) use period= to avoid a race
    # condition in yfinance 1.4.x singleton session when called from threads:
    # start/end date arithmetic triggers double-timeout in requests.Session.request().
    if ticker_sym.startswith("^"):
        period_map = {1: "5d", 7: "1mo", 30: "3mo", 90: "6mo", 120: "1y", 252: "2y"}
        period = next((v for k, v in sorted(period_map.items()) if days <= k), "2y")
        df = yf.download(
            ticker_sym,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
    else:
        end = datetime.now()
        start = end - timedelta(days=days + 10)
        df = yf.download(
            ticker_sym,
            start=start,
            end=end,
            interval=interval,
            progress=False,
            auto_adjust=True,
            timeout=_YF_TIMEOUT,
        )
    if df.empty:
        raise ValueError(f"yfinance returned no data for {ticker_sym}")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[~df.index.duplicated(keep="last")]
    return df.tail(days)


# ── Public API ───────────────────────────────────────────────────────────


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
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
            cached = cached[~cached.index.duplicated(keep="last")]
            cached.attrs["bars_fetched"] = len(cached)
            cached.attrs["bars_requested"] = days
            return cached

    df = None

    if interval == "1d" and exchange == "NSE":
        # 1. Angel One (primary — if configured)
        if settings.ANGEL_API_KEY and settings.ANGEL_CLIENT_ID:
            try:
                df = _fetch_angelone(symbol, days)
                logger.info("OHLCV for %s via Angel One (%d rows)", symbol, len(df))
            except Exception as e:
                logger.warning(
                    "Angel One failed for %s: %s — falling back to jugaad", symbol, e
                )

        # 2. jugaad-data fallback
        if df is None:
            try:
                df = _fetch_jugaad(symbol, days)
                logger.info("OHLCV for %s via jugaad-data (%d rows)", symbol, len(df))
            except Exception as e:
                logger.warning(
                    "jugaad-data failed for %s: %s — falling back to yfinance",
                    symbol,
                    e,
                )

    # 3. yfinance final fallback
    if df is None:
        df = _fetch_yfinance(symbol, days, interval, exchange)
        logger.info("OHLCV for %s via yfinance (%d rows)", symbol, len(df))

    if interval == "1d":
        _write_cache(symbol, days, df)

    df.attrs["bars_fetched"] = len(df)
    df.attrs["bars_requested"] = days
    return df


def fetch_live_price(symbol: str, exchange: str = "NSE") -> float:
    """Returns current market price (or last close). Tries jugaad-data first, then yfinance."""
    # jugaad-data live quotes (NSE only, works from Indian IPs)
    if exchange == "NSE":
        try:
            import concurrent.futures
            from jugaad_data.nse import NSELive

            def _live_quote():
                return NSELive().stock_quote(_bare_symbol(symbol))

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                q = ex.submit(_live_quote).result(timeout=10)
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

    df = df.copy()
    n = len(df)
    df.ta.ema(length=9, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=21, append=True)
    if n >= 50:
        df.ta.ema(length=50, append=True)
    if n >= 200:
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

    subset = [c for c in ["EMA_9", "RSI_14"] if c in df.columns]
    return (
        df.dropna(subset=subset) if subset else df.iloc[0:0]
    )  # empty if no indicators computed
