from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from plutus.data.providers.yfinance_provider import YFinanceProvider

# Index tickers (^INDIAVIX, ^NSEI) are intentionally fetched via yfinance.
# AngelOne Smart API exposes only NSE/BSE equity instruments (token-based),
# not cash-market indices — there is no candle endpoint for these tickers.
_VIX_TICKER = "^INDIAVIX"
_NIFTY_TICKER = "^NSEI"
_LOOKBACK = 252  # 1 year of daily data


def fetch_india_vix(end: date | None = None) -> float:
    """Latest India VIX value from yfinance."""
    from datetime import date as d_
    end = end or d_.today()
    start = end - timedelta(days=30)
    try:
        df = YFinanceProvider().fetch(_VIX_TICKER, start, end)
        return float(df["close"].iloc[-1])
    except Exception:
        return 15.0  # fallback: neutral VIX


def fetch_nifty_candles(lookback_days: int = _LOOKBACK, end: date | None = None) -> pd.DataFrame:
    from datetime import date as d_
    end = end or d_.today()
    start = end - timedelta(days=lookback_days + 50)
    return YFinanceProvider().fetch(_NIFTY_TICKER, start, end)


def compute_breadth_from_candles(
    all_candles: dict[str, pd.DataFrame],
    window: int,
    as_of: date,
) -> tuple[float, float]:
    """Compute (pct_above_50dma, pct_above_200dma) for the universe on as_of date.

    all_candles: {symbol -> df with 'date' and 'close' columns}.
    Returns fractions in [0, 1].
    """
    above_50 = 0
    above_200 = 0
    total = 0
    as_of_ts = pd.Timestamp(as_of)
    for candles in all_candles.values():
        upto = candles[candles["date"] <= as_of_ts]
        if len(upto) < 200:
            continue
        close = upto["close"]
        price = float(close.iloc[-1])
        dma50 = float(close.rolling(50).mean().iloc[-1])
        dma200 = float(close.rolling(200).mean().iloc[-1])
        total += 1
        if price > dma50:
            above_50 += 1
        if price > dma200:
            above_200 += 1
    if total == 0:
        return 0.5, 0.5
    return above_50 / total, above_200 / total


def compute_advance_decline(all_candles: dict[str, pd.DataFrame], as_of: date) -> float:
    """Simple A/D: fraction of universe with positive 1-day return on as_of."""
    as_of_ts = pd.Timestamp(as_of)
    advances = declines = 0
    for candles in all_candles.values():
        upto = candles[candles["date"] <= as_of_ts].tail(2)
        if len(upto) < 2:
            continue
        if float(upto["close"].iloc[-1]) > float(upto["close"].iloc[-2]):
            advances += 1
        else:
            declines += 1
    total = advances + declines
    return advances / total if total else 1.0
