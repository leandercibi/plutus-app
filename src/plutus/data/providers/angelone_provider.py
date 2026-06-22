from __future__ import annotations

import logging
import threading
import time
from datetime import date, timedelta

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_INSTRUMENT_CACHE: dict[str, str] = {}
_INSTRUMENT_LOCK = threading.Lock()

_SESSION_CACHE: dict[str, object] = {}
_SESSION_LOCK = threading.Lock()

_RATE_LOCK = threading.Lock()
_LAST_CALL = [0.0]
_MIN_INTERVAL = 1.0  # 1 request per second


def _load_instruments() -> dict[str, str]:
    global _INSTRUMENT_CACHE
    with _INSTRUMENT_LOCK:
        if _INSTRUMENT_CACHE:
            return _INSTRUMENT_CACHE
        resp = requests.get(
            "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json",
            timeout=20,
        )
        resp.raise_for_status()
        instruments = resp.json()
        _INSTRUMENT_CACHE = {
            i["symbol"].upper().replace("-EQ", ""): i["token"]
            for i in instruments
            if i.get("exch_seg") == "NSE" and i.get("symbol", "").endswith("-EQ")
        }
        logger.info("angel_instruments_loaded: %d NSE equities", len(_INSTRUMENT_CACHE))
        return _INSTRUMENT_CACHE


def _resolve_token(symbol: str) -> str:
    instruments = _load_instruments()
    token = instruments.get(symbol.upper())
    if token is None:
        raise ValueError(f"No Angel One token for {symbol}")
    return token


def _get_session(api_key: str, client_id: str, password: str, totp_secret: str):
    with _SESSION_LOCK:
        if _SESSION_CACHE.get("obj"):
            return _SESSION_CACHE["obj"]
        import pyotp
        from SmartApi import SmartConnect

        obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        data = obj.generateSession(client_id, password, totp)
        if not data or data.get("status") is False:
            raise ConnectionError(f"Angel One login failed: {data}")
        _SESSION_CACHE["obj"] = obj
        logger.info("angel_session_created for client %s", client_id)
        return obj


def _rate_wait() -> None:
    with _RATE_LOCK:
        now = time.monotonic()
        elapsed = now - _LAST_CALL[0]
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _LAST_CALL[0] = time.monotonic()


def invalidate_session() -> None:
    with _SESSION_LOCK:
        _SESSION_CACHE.clear()


class AngelOneProvider:
    def __init__(
        self,
        api_key: str,
        client_id: str,
        password: str,
        totp_secret: str,
    ) -> None:
        self._api_key = api_key
        self._client_id = client_id
        self._password = password
        self._totp_secret = totp_secret

    def _session(self):
        return _get_session(
            self._api_key, self._client_id, self._password, self._totp_secret,
        )

    def fetch_ltp(self, symbol: str) -> float:
        token = _resolve_token(symbol)
        _rate_wait()
        obj = self._session()
        resp = obj.ltpData("NSE", symbol.upper() + "-EQ", token)
        if not resp or resp.get("status") is False:
            raise ValueError(f"Angel One LTP failed for {symbol}: {resp}")
        data = resp.get("data", {})
        ltp = data.get("ltp")
        if ltp is None:
            raise ValueError(f"No LTP in Angel One response for {symbol}: {data}")
        return float(ltp)

    def fetch_ltp_batch(self, symbols: list[str]) -> dict[str, float]:
        prices: dict[str, float] = {}
        for sym in symbols:
            try:
                prices[sym] = self.fetch_ltp(sym)
            except Exception:
                logger.warning("angel_ltp_failed: %s", sym, exc_info=True)
        return prices

    def _getCandleData(self, symbol: str, interval: str, start: date, end: date) -> pd.DataFrame:
        token = _resolve_token(symbol)
        _rate_wait()
        obj = self._session()
        params = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": interval,
            "fromdate": f"{start.isoformat()} 09:00",
            "todate": f"{(end + timedelta(days=1)).isoformat()} 15:30",
        }
        data = obj.getCandleData(params)
        if not data or not data.get("data"):
            raise ValueError(f"Angel One returned no candle data for {symbol}")
        df = pd.DataFrame(
            data["data"],
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["date"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        return df[["date", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        return self._getCandleData(symbol, "ONE_DAY", start, end)

    def fetch_intraday(self, symbol: str, days: int = 60, interval: str = "ONE_HOUR") -> pd.DataFrame:
        """Fetch intraday OHLCV. Angel One supports ONE_HOUR for up to ~400 days."""
        end = date.today()
        start = end - timedelta(days=days)
        return self._getCandleData(symbol, interval, start, end)
