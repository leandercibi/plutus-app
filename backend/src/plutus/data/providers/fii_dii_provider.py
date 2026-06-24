from __future__ import annotations

# NOTE: Real NSE FII/DII daily flows are published at
# https://www.nseindia.com/market-data/fii-dii-activity — there is no
# reliable free API. This stub approximates flows from NIFTY price action.
# Replace with a real scraper/feed when NSE data becomes available.
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_CRORE = 10_000_000  # 1 crore rupees in rupees
_FII_SCALE = 3000 * _CRORE  # ~₹3000 crore typical daily FII flow magnitude
_DII_COUNTER_RATIO = 0.6
_RNG_SEED = 42


class FIIDIIStubProvider:
    """Approximate FII/DII flows from NIFTY daily returns.

    FII flow ≈ NIFTY pct-change × scale.
    DII flow ≈ -FII × 0.6 (DII tends to counter FII on net).
    """

    def fetch(self, start: date, end: date) -> pd.DataFrame:
        try:
            raw = yf.download(
                "^NSEI", start=start - timedelta(days=10),
                end=end + timedelta(days=1),
                auto_adjust=True, progress=False,
            )
            if raw.empty:
                raise ValueError("empty")
            close = raw["Close"].squeeze()
            close.index = pd.to_datetime(close.index).normalize()
            pct = close.pct_change().fillna(0.0)
            rng = np.random.default_rng(_RNG_SEED)
            noise = rng.normal(0, 0.15, size=len(pct))
            fii = pct * _FII_SCALE
            dii = -fii * _DII_COUNTER_RATIO + pd.Series(
                noise * _FII_SCALE * 0.1, index=pct.index
            )
            df = pd.DataFrame(
                {"fii_net_inr_crore": fii / _CRORE, "dii_net_inr_crore": dii / _CRORE},
                index=pct.index,
            )
            return df.loc[str(start):str(end)]
        except Exception as exc:
            logger.warning("FII/DII stub fetch failed: %s; returning zeros", exc)
            idx = pd.date_range(start, end, freq="B")
            return pd.DataFrame(
                {"fii_net_inr_crore": 0.0, "dii_net_inr_crore": 0.0}, index=idx
            )
