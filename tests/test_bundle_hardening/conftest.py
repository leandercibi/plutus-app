# tests/test_bundle_hardening/conftest.py
"""
Synthetic OHLCV fixtures for bundle hardening tests — no network calls.

Each fixture is engineered to guarantee signals for its target bundle:
  bull_df    → multiple EMA9×EMA21 crossovers with price above EMA50 and ADX>18
  sideways_df → oscillates so RSI dips below 40 near lower Bollinger band
  volatile_df → large-range bars triggering liquidity-grab patterns
"""
from __future__ import annotations

import os
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "-1")

from datetime import date

import backtrader as bt
import numpy as np
import pandas as pd
import pytest


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range(end=date.today(), periods=n, freq="B")


def make_bull_df(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """
    Bull DataFrame with 5 mini-waves in a strong uptrend.
    Each wave: 20-bar dip (EMA9 < EMA21) then 40-bar rally (EMA9 crosses back up).
    Price stays above EMA50 after bar 80 (EMA50 has caught up).
    Volume spikes 2× on each rally start.
    """
    rng = np.random.default_rng(seed)

    # Phase 0 (bars 0-79): establishing EMA50 baseline with mild uptrend
    base = 1000.0
    prices, vols = [], []
    for i in range(80):
        base *= (1 + 0.002 + rng.normal(0, 0.006))
        prices.append(base)
        vols.append(float(rng.integers(800_000, 1_200_000)))

    # Phase 1 (bars 80-300): 3 full wave cycles — dip then rally
    for wave in range(3):
        # dip: 20 bars
        for i in range(20):
            base *= (1 - 0.003 + rng.normal(0, 0.007))
            prices.append(base)
            vols.append(float(rng.integers(600_000, 1_000_000)))
        # rally: 47 bars — strong enough to push ADX > 18 and clear EMA50
        for i in range(47):
            base *= (1 + 0.008 + rng.normal(0, 0.005))
            prices.append(base)
            mult = 2.5 if i < 10 else 1.0   # volume spike on breakout bars
            vols.append(float(rng.integers(800_000, 1_200_000) * mult))

    closes = np.array(prices[:n], dtype=float)
    highs  = closes * (1 + rng.uniform(0.003, 0.010, len(closes)))
    lows   = closes * (1 - rng.uniform(0.003, 0.010, len(closes)))
    return pd.DataFrame(
        {"Open": closes, "High": highs, "Low": lows, "Close": closes,
         "Volume": np.array(vols[:n], dtype=float)},
        index=_dates(len(closes)),
    )


def make_bear_df(n: int = 200, seed: int = 7) -> pd.DataFrame:
    rng  = np.random.default_rng(seed)
    base = 1000.0
    prices, vols = [], []
    for _ in range(n):
        base = max(100.0, base * (1 - 0.004 + rng.normal(0, 0.010)))
        prices.append(base)
        vols.append(float(rng.integers(800_000, 1_200_000)))
    closes = np.array(prices, dtype=float)
    highs  = closes * (1 + rng.uniform(0.003, 0.010, n))
    lows   = closes * (1 - rng.uniform(0.003, 0.010, n))
    return pd.DataFrame(
        {"Open": closes, "High": highs, "Low": lows, "Close": closes,
         "Volume": np.array(vols, dtype=float)},
        index=_dates(n),
    )


def make_reversal_df(n: int = 250, seed: int = 13) -> pd.DataFrame:
    """
    Data engineered for ReversalBundle: repeat 3× the cycle of
      30-bar steep decline (RSI→20, MACD deeply negative) then
      1 reversal bar (high-volume bullish outside bar near BB lower band)
      then 20-bar recovery.

    The reversal bar has MACD starting to turn up (MACD[0] > MACD[-1])
    because the decline was steep — MACD lines diverge, then snap back on
    the strong reversal candle.
    """
    rng  = np.random.default_rng(seed)
    prices, opens_l, highs_l, lows_l, vols = [], [], [], [], []

    base = 1200.0
    for cycle in range(3):
        # 30-bar decline: -0.8%/day → RSI ≈ 20, MACD deeply negative
        for i in range(30):
            base = max(200.0, base * (1 - 0.008 + rng.normal(0, 0.005)))
            o = base * 1.002
            c = base
            prices.append(c); opens_l.append(o)
            highs_l.append(max(o, c) * 1.003)
            lows_l.append(min(o, c) * 0.997)
            vols.append(float(rng.integers(800_000, 1_200_000)))
        # 2 reversal bars: strong bullish close — MACD starts turning, RSI still <40
        for i in range(2):
            o = base * 0.985
            c = base * 1.025    # 4% bullish bar
            base = c
            prices.append(c); opens_l.append(o)
            highs_l.append(c * 1.005)
            lows_l.append(o * 0.993)
            vols.append(float(rng.integers(1_800_000, 2_600_000)))  # vol spike
        # 20-bar recovery
        for i in range(20):
            base *= (1 + 0.005 + rng.normal(0, 0.006))
            o = base * 0.999; c = base
            prices.append(c); opens_l.append(o)
            highs_l.append(c * 1.005); lows_l.append(o * 0.995)
            vols.append(float(rng.integers(800_000, 1_200_000)))

    total = len(prices)
    return pd.DataFrame(
        {"Open": np.array(opens_l[:n]), "High": np.array(highs_l[:n]),
         "Low": np.array(lows_l[:n]), "Close": np.array(prices[:n]),
         "Volume": np.array(vols[:n])},
        index=_dates(min(n, total)),
    )


def make_sideways_df(n: int = 200, seed: int = 13) -> pd.DataFrame:
    """Alias kept for backward compat — now returns reversal-friendly data."""
    return make_reversal_df(n=n, seed=seed)


def make_volatile_df(n: int = 200, seed: int = 99) -> pd.DataFrame:
    """
    Every 7 bars: a bullish liquidity-grab candle.
    The bar's LOW dips below the previous 5-bar min, then CLOSES bullish (close > open).
    Volume 2.5× on those bars. RSI stays 30–65 (mild uptrend between grabs).
    """
    rng    = np.random.default_rng(seed)
    base   = 500.0
    opens_l, closes_l, highs_l, lows_l, vols = [], [], [], [], []
    for i in range(n):
        move = rng.normal(0.001, 0.010)   # mild uptrend between grabs
        base = max(50.0, base * (1 + move))
        grab = (i % 7 == 0 and i > 10)
        if grab:
            open_  = base * 0.970   # opens low (gap-down look)
            close_ = base * 1.005   # closes back above open (bullish recovery)
            lo     = base * 0.950   # wick dips below recent low
            hi     = base * 1.015
        else:
            open_  = base * (1 - rng.uniform(0, 0.003))
            close_ = base
            lo     = base * (1 - rng.uniform(0.003, 0.010))
            hi     = base * (1 + rng.uniform(0.003, 0.010))
        opens_l.append(open_)
        closes_l.append(close_)
        lows_l.append(lo)
        highs_l.append(hi)
        vols.append(float(rng.integers(800_000, 1_200_000) * (2.5 if grab else 1.0)))
    return pd.DataFrame(
        {"Open": np.array(opens_l), "High": np.array(highs_l),
         "Low": np.array(lows_l), "Close": np.array(closes_l),
         "Volume": np.array(vols)},
        index=_dates(n),
    )


def make_vcp_df(n: int = 200, seed: int = 99) -> pd.DataFrame:
    """
    Data engineered for VCPBundle: uptrend → 3 contracting ATR stages → pivot breakout.

    Layout (indices 0-based):
      0–89   : gentle uptrend (EMA50 warmup, ~0.3%/bar)
      90–94  : Phase 0.5 — very wide range ±5% (becomes atrs[3] in VCP check)
      95–99  : Stage C — range ±3%  (atrs[2])
      100–104: Stage B — range ±2%  (atrs[1])
      105–109: Stage A — range ±1%  (atrs[0] along with breakout bar)
      110    : Breakout bar — close > 20-bar pivot high, volume 2×
    """
    rng = np.random.default_rng(seed)
    opens, highs, lows, closes, vols = [], [], [], [], []
    base = 1000.0

    # Phase 0: 90-bar uptrend
    for _ in range(90):
        base *= (1 + 0.003 + rng.normal(0, 0.003))
        c = float(base)
        closes.append(c)
        highs.append(c * (1 + rng.uniform(0.003, 0.010)))
        lows.append(c * (1 - rng.uniform(0.003, 0.010)))
        opens.append(c)
        vols.append(float(rng.integers(900_000, 1_100_000)))

    # Alternating up/down multipliers to keep RSI in [50, 70] during consolidation.
    # All-positive drift pushes RSI → 100 which blocks the RSI check in has_long_signal().
    _alt_ctr = [0]

    def _stage(h_mult: float, l_mult: float, vol: float, n_bars: int = 5):
        nonlocal base
        for _ in range(n_bars):
            base *= 1.002 if _alt_ctr[0] % 2 == 0 else 0.998
            _alt_ctr[0] += 1
            c = float(base)
            closes.append(c)
            highs.append(c * h_mult)
            lows.append(c * l_mult)
            opens.append(c)
            vols.append(vol)

    _stage(1.050, 0.950, 800_000.0)  # Phase 0.5 — wide range → atrs[3]
    _stage(1.030, 0.970, 800_000.0)  # Stage C → atrs[2]
    _stage(1.020, 0.980, 800_000.0)  # Stage B → atrs[1]
    _stage(1.010, 0.990, 800_000.0)  # Stage A → part of atrs[0]

    # Breakout bar: close > max of the 20 previous closes, volume surge
    pivot_high    = max(closes[-20:])
    breakout_c    = float(pivot_high * 1.02)
    closes.append(breakout_c)
    highs.append(breakout_c * 1.005)
    lows.append(breakout_c * 0.995)
    opens.append(float(closes[-2] * 1.005))
    vols.append(2_000_000.0)

    # Continuation rally: ensure the trade closes at T1/T2 before random noise takes over.
    # ATR at entry ≈ 46 pts (dominated by Phase 0.5 wide bars via Wilder EWM).
    # T2 = entry + 3 × ATR ≈ entry + 138, requiring ~10% rally.  30 bars × 0.5%/bar
    # reaches that comfortably, keeping pnl_pct positive for trade-sanity assertions.
    for _ in range(35):
        base = closes[-1] * (1 + 0.005 + float(rng.normal(0, 0.002)))
        closes.append(float(base))
        highs.append(float(base * 1.008))
        lows.append(float(base * 0.992))
        opens.append(float(base))
        vols.append(1_000_000.0)

    # Pad remainder with low-noise random walk
    while len(closes) < n:
        base = closes[-1] * (1 + float(rng.normal(0, 0.003)))
        closes.append(base)
        highs.append(base * 1.01)
        lows.append(base * 0.99)
        opens.append(base)
        vols.append(1_000_000.0)

    sz = min(len(closes), n)
    return pd.DataFrame(
        {"Open": opens[:sz], "High": highs[:sz], "Low": lows[:sz],
         "Close": closes[:sz], "Volume": vols[:sz]},
        index=_dates(sz),
    )


def make_pead_df(n: int = 200, seed: int = 55) -> pd.DataFrame:
    """
    Data engineered for PEADBundle: gentle uptrend → earnings gap-up → EMA10 pullback entry.

    Layout (0-based):
      0–129  : gentle uptrend (~0.3%/bar, EMA10/EMA50 warmup)
      130    : Earnings gap bar — open = prev_close × 1.07, volume = 3M
      131    : First pullback — close slightly above EMA10×1.02 (no entry yet)
      132    : Second pullback — close ≤ EMA10×1.02 → entry fires
      133–152: Continuation rally → trade closes at T1 or T2
    """
    rng = np.random.default_rng(seed)
    opens, highs, lows, closes, vols = [], [], [], [], []
    base = 1000.0

    # Phase 0: 130-bar uptrend
    for _ in range(130):
        base *= (1 + 0.003 + rng.normal(0, 0.003))
        c = float(base)
        closes.append(c)
        highs.append(c * 1.008)
        lows.append(c * 0.992)
        opens.append(c)
        vols.append(float(rng.integers(900_000, 1_100_000)))

    # Earnings gap bar: 7% gap-up, 3M volume (≥ 2 × ~1M avg)
    prev_c    = closes[-1]
    gap_open  = float(prev_c * 1.07)
    gap_close = float(prev_c * 1.04)
    closes.append(gap_close); highs.append(gap_close * 1.010)
    lows.append(gap_close * 0.995); opens.append(gap_open)
    vols.append(3_000_000.0)

    # Pullback bars — price retraces toward EMA10
    # EMA10 lags ~1.6% below price in steady uptrend; after the gap it needs 2+ bars to
    # catch up. Bar 131 is still above EMA10×1.02; bar 132 dips into the entry zone.
    for i in range(1, 5):
        pull_c = float(gap_close * (1 - 0.015 * i))
        closes.append(pull_c)
        highs.append(pull_c * 1.005)
        lows.append(pull_c * 0.995)
        opens.append(pull_c * 1.003)
        vols.append(float(rng.integers(1_000_000, 1_500_000)))

    # Continuation rally — trade exits at T1 or T2
    for _ in range(25):
        base = closes[-1] * (1 + 0.006 + rng.normal(0, 0.003))
        closes.append(float(base))
        highs.append(float(base * 1.008))
        lows.append(float(base * 0.992))
        opens.append(float(base))
        vols.append(float(rng.integers(900_000, 1_100_000)))

    # Pad to n
    while len(closes) < n:
        base = closes[-1] * (1 + float(rng.normal(0, 0.005)))
        closes.append(base)
        highs.append(base * 1.01)
        lows.append(base * 0.99)
        opens.append(base)
        vols.append(1_000_000.0)

    sz = min(len(closes), n)
    return pd.DataFrame(
        {"Open": opens[:sz], "High": highs[:sz], "Low": lows[:sz],
         "Close": closes[:sz], "Volume": vols[:sz]},
        index=_dates(sz),
    )


def run_strategy(df: pd.DataFrame, strategy_cls, **params) -> bt.Strategy:
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addstrategy(strategy_cls, **params)
    cerebro.broker.setcash(100_000)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    return cerebro.run()[0]


@pytest.fixture
def bull_df():
    return make_bull_df()


@pytest.fixture
def bear_df():
    return make_bear_df()


@pytest.fixture
def sideways_df():
    return make_sideways_df()


@pytest.fixture
def volatile_df():
    return make_volatile_df()


@pytest.fixture
def vcp_df():
    return make_vcp_df()


@pytest.fixture
def pead_df():
    return make_pead_df()
