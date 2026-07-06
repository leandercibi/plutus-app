from __future__ import annotations

import logging
import threading
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_INSTRUMENT_CACHE: dict[str, str] = {}
_INSTRUMENT_LOCK = threading.Lock()

_SESSION_CACHE: dict[str, object] = {}  # keys: "obj", "refresh_token"
_SESSION_LOCK = threading.Lock()

_RATE_LOCK = threading.Lock()
_LAST_CALL = [0.0]
_MIN_INTERVAL = 0.34  # ~3 requests/second — AngelOne Smart API historical candle limit

# How long a *user-facing* call waits to acquire the rate-limit slot before giving up.
# Background jobs pass None (block indefinitely); API handlers pass this constant.
USER_RATE_LIMIT_TIMEOUT = 5.0


class RateLimitSaturated(Exception):
    """Raised when the rate-limit slot cannot be acquired within the timeout.

    Callers on the user-facing path should catch this and fall back to yfinance
    rather than surfacing a 503 to the browser.
    """


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


def _get_session(
    api_key: str, client_id: str, password: str, totp_secret: str, force: bool = False
) -> Any:
    with _SESSION_LOCK:
        if not force and _SESSION_CACHE.get("obj"):
            return _SESSION_CACHE["obj"]

        from SmartApi import SmartConnect

        obj: Any = _SESSION_CACHE.get("obj") or SmartConnect(api_key=api_key)

        # Prefer token refresh (no TOTP) if we have a refresh_token
        refresh_token = _SESSION_CACHE.get("refresh_token")
        if force and refresh_token:
            try:
                resp = obj.generateToken(refresh_token)
                if resp and resp.get("status") is not False:
                    _SESSION_CACHE["obj"] = obj
                    logger.info("angel_session_token_refreshed for client %s", client_id)
                    return obj
            except Exception:
                logger.warning(
                    "angel_token_refresh_failed — falling back to full TOTP login", exc_info=True
                )

        # Full TOTP re-login
        import pyotp

        if not isinstance(obj, SmartConnect) or force:
            obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        data = obj.generateSession(client_id, password, totp)
        if not data or data.get("status") is False:
            raise ConnectionError(f"Angel One login failed: {data}")
        _SESSION_CACHE["obj"] = obj
        _SESSION_CACHE["refresh_token"] = data["data"]["refreshToken"]
        logger.info("angel_session_%s for client %s", "relogin" if force else "created", client_id)
        return obj


def _rate_wait(timeout: float | None = None) -> None:
    """Acquire the rate-limit slot, then enforce the minimum inter-call interval.

    Args:
        timeout: seconds to wait for the lock.  ``None`` (default) blocks
            indefinitely — correct for background pipeline jobs.  Pass a
            positive float for user-facing calls so they fail fast rather than
            queueing behind a running pipeline sweep.

    Raises:
        RateLimitSaturated: if the lock cannot be acquired within *timeout*.
    """
    # Lock.acquire(timeout=-1) blocks indefinitely; any positive float limits it.
    acquired = _RATE_LOCK.acquire(blocking=True, timeout=-1 if timeout is None else timeout)
    if not acquired:
        raise RateLimitSaturated(
            f"AngelOne rate limiter saturated — slot not available within {timeout}s. "
            "A background pipeline may be running; retry shortly."
        )
    try:
        elapsed = time.monotonic() - _LAST_CALL[0]
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _LAST_CALL[0] = time.monotonic()
    finally:
        _RATE_LOCK.release()


def invalidate_session() -> None:
    """Clear the cached session object but keep the refresh_token for renewal."""
    with _SESSION_LOCK:
        _SESSION_CACHE.pop("obj", None)


class AngelOneProvider:
    name: str = "angelone"
    adjustment: str = "split_adjusted"

    def __init__(
        self,
        api_key: str,
        client_id: str,
        password: str,
        totp_secret: str,
        *,
        rate_limit_timeout: float | None = None,
    ) -> None:
        self._api_key = api_key
        self._client_id = client_id
        self._password = password
        self._totp_secret = totp_secret
        # None  → block indefinitely (background pipeline jobs)
        # float → fail fast (user-facing API handlers)
        self._rate_limit_timeout = rate_limit_timeout

    def _session(self, force: bool = False) -> Any:
        return _get_session(
            self._api_key,
            self._client_id,
            self._password,
            self._totp_secret,
            force=force,
        )

    def fetch_ltp(self, symbol: str) -> float:
        token = _resolve_token(symbol)
        for attempt in range(2):
            _rate_wait(self._rate_limit_timeout)
            obj = self._session(force=(attempt == 1))
            resp = obj.ltpData("NSE", symbol.upper() + "-EQ", token)
            if not resp or resp.get("status") is False:
                if attempt == 0:
                    logger.warning("angel_ltp_auth_expired: %s — refreshing session", symbol)
                    invalidate_session()
                    continue
                raise ValueError(f"Angel One LTP failed for {symbol}: {resp}")
            data = resp.get("data", {})
            ltp = data.get("ltp")
            if ltp is None:
                raise ValueError(f"No LTP in Angel One response for {symbol}: {data}")
            return float(ltp)
        raise ValueError(f"Angel One LTP failed for {symbol} after session refresh")

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
        params = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": interval,
            "fromdate": f"{start.isoformat()} 09:00",
            "todate": f"{(end + timedelta(days=1)).isoformat()} 15:30",
        }
        for attempt in range(2):
            _rate_wait(self._rate_limit_timeout)
            obj = self._session(force=(attempt == 1))
            data = obj.getCandleData(params)
            if not data or not data.get("data"):
                if attempt == 0:
                    logger.warning("angel_candle_auth_expired: %s — refreshing session", symbol)
                    invalidate_session()
                    continue
                raise ValueError(f"Angel One returned no candle data for {symbol}")
            df = pd.DataFrame(
                data["data"],
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["date"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
            return df[["date", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])
        raise ValueError(f"Angel One candle fetch failed for {symbol} after session refresh")

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        return self._getCandleData(symbol, "ONE_DAY", start, end)

    def fetch_intraday(
        self, symbol: str, days: int = 60, interval: str = "ONE_HOUR"
    ) -> pd.DataFrame:
        """Fetch intraday OHLCV. Angel One supports ONE_HOUR for up to ~400 days."""
        end = date.today()
        start = end - timedelta(days=days)
        return self._getCandleData(symbol, interval, start, end)
