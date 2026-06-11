from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TechnicalScore:
    """A10 — a single collapsed trend-momentum factor (0..30), de-correlated.

    Trend alignment + RSI + MACD are treated as ONE factor (not three additive
    pillars). Freed weight goes to ATR percentile and a mean-reversion flag.
    """

    trend_momentum: float  # 0..18
    atr_percentile: float  # 0..6
    mean_reversion: float  # 0..6
    total: int  # 0..30


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0


def _macd_hist(close: pd.Series) -> float:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return float((macd - signal).iloc[-1])


def technical_score(candles: pd.DataFrame) -> TechnicalScore:
    """A3/A10. Consumes raw price/momentum features ONLY.

    MUST NOT take per-stock Sharpe / BundleStatPerRegime as input. The CI static
    check (test_pillars_no_per_stock_sharpe_leak) enforces the no-import rule.
    """
    close = candles["close"]
    dma50 = close.rolling(50).mean().iloc[-1]
    dma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else dma50
    price = float(close.iloc[-1])

    aligned = price > dma50 > dma200
    rsi = _rsi(close)
    macd_pos = _macd_hist(close) > 0

    trend_momentum = 0.0
    if aligned:
        trend_momentum += 9.0
    if 50 <= rsi <= 70:
        trend_momentum += 5.0
    elif rsi > 70:
        trend_momentum += 2.0
    if macd_pos:
        trend_momentum += 4.0

    high = candles["high"]
    low = candles["low"]
    tr = (high - low).rolling(14).mean()
    atr_pct_series = (tr / close).dropna()
    if len(atr_pct_series) >= 2:
        rank = (atr_pct_series.rank(pct=True)).iloc[-1]
        atr_percentile = float(rank) * 6.0
    else:
        atr_percentile = 0.0

    mean_reversion = 6.0 if rsi < 35 else 0.0

    total = int(round(min(30.0, trend_momentum + atr_percentile + mean_reversion)))
    return TechnicalScore(
        trend_momentum=trend_momentum,
        atr_percentile=atr_percentile,
        mean_reversion=mean_reversion,
        total=total,
    )
