from __future__ import annotations

from datetime import date, timedelta
from typing import ClassVar

import pandas as pd

from plutus.data.base import AdjustmentPolicy

# NSE symbols in yfinance require the .NS suffix
_NS_SUFFIX = ".NS"
_NIFTY_TICKER = "^NSEI"


def _to_yf(symbol: str) -> str:
    if symbol.startswith("^") or "." in symbol:
        return symbol
    return symbol + _NS_SUFFIX


class YFinanceProvider:
    """Primary OHLCV provider backed by yfinance (split+dividend adjusted)."""

    name: ClassVar[str] = "yfinance"
    adjustment: ClassVar[AdjustmentPolicy] = "split_and_dividend"

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        import yfinance as yf  # import here so tests can stub at module level

        ticker = yf.Ticker(_to_yf(symbol))
        raw = ticker.history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=True,
        )
        if raw.empty:
            raise ValueError(f"yfinance returned empty DataFrame for {symbol}")

        df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]  # type: ignore[assignment]
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.index.name = "date"
        df = df.reset_index()
        df["date"] = pd.to_datetime(df["date"])
        return df.dropna(subset=["close"])


class NiftyProvider:
    """Convenience wrapper to fetch NIFTY 50 index candles via yfinance."""

    name: ClassVar[str] = "yfinance_nifty"
    adjustment: ClassVar[AdjustmentPolicy] = "split_adjusted"

    def fetch(self, start: date, end: date) -> pd.DataFrame:
        return YFinanceProvider().fetch(_NIFTY_TICKER, start, end)
