from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import cast

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ^INDIAVIX is a cash-market index — AngelOne doesn't expose it via candle API.
# yfinance is intentional here.
_NEUTRAL_VIX = 15.0
_TICKER = "^INDIAVIX"


class VixYFinanceProvider:
    def fetch(self, start: date, end: date) -> pd.Series:
        try:
            df = yf.download(
                _TICKER, start=start, end=end + timedelta(days=1), auto_adjust=True, progress=False
            )
            if df.empty:
                raise ValueError("empty")
            close = df["Close"]
            if hasattr(close, "squeeze"):
                close = close.squeeze()
            close.index = pd.to_datetime(close.index).normalize()
            return cast(pd.Series, close.sort_index().dropna())
        except Exception as exc:
            logger.warning("VIX fetch failed (%s); using neutral %.1f", exc, _NEUTRAL_VIX)
            idx = pd.date_range(start, end, freq="B")
            return pd.Series(_NEUTRAL_VIX, index=idx)

    def latest(self) -> float:
        today = date.today()
        s = self.fetch(today - timedelta(days=10), today)
        return float(s.iloc[-1]) if not s.empty else _NEUTRAL_VIX
