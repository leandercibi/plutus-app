from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TechnicalScore:
    """A10 — a single collapsed trend-momentum factor (0..30), de-correlated.

    Trend alignment + RSI + MACD are treated as ONE factor (not three additive
    pillars). Freed weight goes to ATR percentile and a mean-reversion flag.
    MACD crossover + Bollinger squeeze combo adds bonus points.
    """

    trend_momentum: float  # 0..18
    atr_percentile: float  # 0..6
    mean_reversion: float  # 0..6
    macd_cross_bonus: float  # 0..4
    bollinger_squeeze_bonus: float  # 0..3
    total: int  # 0..30


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0


def _macd_components(close: pd.Series) -> tuple[float, float, float]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return float(macd.iloc[-1]), float(signal.iloc[-1]), float(hist.iloc[-1])


def _macd_crossover(close: pd.Series) -> bool:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    if len(macd) < 3:
        return False
    return bool(macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2])


def _bollinger_squeeze(close: pd.Series, lookback: int = 5) -> bool:
    bb_std = close.rolling(20).std()
    bb_mid = close.rolling(20).mean()
    if bb_mid.iloc[-1] == 0 or len(bb_std.dropna()) < lookback + 1:
        return False
    width = (bb_std / bb_mid).dropna()
    if len(width) < lookback + 1:
        return False
    recent_width = float(width.iloc[-1])
    min_width = float(width.iloc[-(lookback + 1) : -1].min())
    expanding = recent_width > min_width * 1.1
    price = float(close.iloc[-1])
    upper = float(bb_mid.iloc[-1] + 2 * bb_std.iloc[-1])
    breakout = price > upper * 0.98
    return bool(expanding and breakout)


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
    _macd_val, _macd_sig, macd_h = _macd_components(close)
    macd_pos = macd_h > 0

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

    macd_cross_bonus = 4.0 if _macd_crossover(close) else 0.0
    bb_squeeze_bonus = 3.0 if _bollinger_squeeze(close) else 0.0

    raw = trend_momentum + atr_percentile + mean_reversion + macd_cross_bonus + bb_squeeze_bonus
    total = int(round(min(30.0, raw)))
    return TechnicalScore(
        trend_momentum=trend_momentum,
        atr_percentile=atr_percentile,
        mean_reversion=mean_reversion,
        macd_cross_bonus=macd_cross_bonus,
        bollinger_squeeze_bonus=bb_squeeze_bonus,
        total=total,
    )
