#!/usr/bin/env python
"""Rebuild ``plutus/data/seed_universe.csv`` from real OHLCV data.

This is the manual helper referenced in ``specs/_CHANGE_SPEC.md`` §2. It does
NOT replace the runtime liquidity gate in ``plutus.data.universe.get_universe``;
it produces a *better candidate pool* by ranking each symbol on liquidity,
trend, momentum and relative strength using the data you already cache.

Why it's cheap on API calls
----------------------------
Every symbol goes through ``plutus.data.ohlcv.fetch_ohlcv`` which:
  * prefers Angel One SmartAPI (if configured),
  * disk-caches each symbol as Parquet for 12h.
So re-running within 12h is free, and a weekly refresh is ~1 call/symbol.
Run it once a week (e.g. Sunday before the pipeline) and the weekly universe
cache reuses the same Parquet files — no extra Angel One load.

How symbols are scored (all from daily OHLCV, no ``Ticker.info``)
-----------------------------------------------------------------
1. HARD GATES (same spirit as get_universe — a symbol must pass all):
     - price in [UNIVERSE_PRICE_MIN, UNIVERSE_PRICE_MAX]
     - 30d avg volume   >= UNIVERSE_MIN_AVG_VOLUME
     - 30d avg turnover >= UNIVERSE_MIN_AVG_VALUE_CR  (₹ Cr/day)
     - at least ~150 bars so EMA50/EMA200 + 6m momentum are meaningful
2. RANK SCORE (0-100, higher = better swing candidate), weighted:
     - liquidity   25%  : log of avg daily turnover (deeper book = safer exits)
     - trend       25%  : close > EMA50 > EMA200 stack, and slope of EMA50
     - momentum    25%  : blended 3m / 6m return (current strength, not all-time)
     - rel_strength15%  : return vs the candidate-pool median (beats the market?)
     - setup       10%  : RSI in a healthy 45-70 band + not overextended from
                          EMA20 (room to run, not already vertical)
   Momentum/relative-strength are measured on *current* data, deliberately
   avoiding the survivorship/recency trap of picking last year's top gainers.

Usage
-----
Run from the code root (``src/``) so the default relative paths resolve::

    cd /Users/leander/personal-projects/plutus-app/src
    python -m scripts.refresh_seed_universe                 # rank current seed pool
    python -m scripts.refresh_seed_universe --add nifty_smallcap250.csv
    python -m scripts.refresh_seed_universe --top 500 --dry-run

Flags:
    --add PATH      Extra candidate CSV (col ``symbol``) merged into the pool,
                    e.g. the liquid Nifty Smallcap 250 list. De-duped.
    --top N         Keep the top-N ranked symbols (default 500).
    --report PATH   Where to write the full ranked report with all metrics
                    (default plutus/data/universe_ranked.csv).
    --dry-run       Print the summary and write the report, but do NOT
                    overwrite seed_universe.csv.
    --min-bars N    Minimum bars required (default 150).
"""
from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from plutus.config import settings
from plutus.data.ohlcv import fetch_ohlcv

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("refresh_seed_universe")

# Number of trading days used for the longer-horizon momentum / RS window.
_MOM_LONG = 126  # ~6 months
_MOM_SHORT = 63  # ~3 months


def _load_candidate_pool(seed_csv: Path, extra_csv: Path | None) -> List[str]:
    """Union of the current seed CSV and an optional extra candidate CSV."""
    symbols: List[str] = []
    for path in (seed_csv, extra_csv):
        if not path:
            continue
        if not path.exists():
            logger.warning("candidate CSV not found, skipping: %s", path)
            continue
        with path.open() as f:
            for row in csv.DictReader(f):
                sym = (row.get("symbol") or "").strip().upper()
                if sym:
                    symbols.append(sym)
    return list(dict.fromkeys(symbols))  # de-dupe, preserve order


def _segment_for_turnover(turnover_cr: float) -> str:
    """Coarse liquidity-tier label written back into the CSV's segment column.

    This is a *liquidity* tier, not an index membership — the existing CSV's
    segment column is informational only (no code reads it).
    """
    if turnover_cr >= 100:
        return "LARGE_CAP"
    if turnover_cr >= 25:
        return "MID_CAP"
    return "SMALL_CAP"


def _compute_metrics(symbol: str, df: pd.DataFrame) -> Dict | None:
    """Return raw per-symbol metrics, or None if it fails the hard gates."""
    if df is None or df.empty:
        return None

    close = df["Close"].astype(float)
    volume = df["Volume"].astype(float)
    last_close = float(close.iloc[-1])

    avg_volume_30d = float(volume.tail(30).mean())
    avg_turnover_cr = float((close * volume).tail(30).mean()) / 1e7

    # ── HARD GATES (mirror get_universe so we never rank un-tradeable names) ──
    if not (settings.UNIVERSE_PRICE_MIN <= last_close <= settings.UNIVERSE_PRICE_MAX):
        return None
    if avg_volume_30d < settings.UNIVERSE_MIN_AVG_VOLUME:
        return None
    if avg_turnover_cr < settings.UNIVERSE_MIN_AVG_VALUE_CR:
        return None

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()

    # Trend stack + EMA50 slope over ~1 month.
    stacked = last_close > ema50.iloc[-1] > ema200.iloc[-1]
    ema50_slope = (
        (ema50.iloc[-1] - ema50.iloc[-21]) / ema50.iloc[-21] if len(ema50) > 21 else 0.0
    )

    # Momentum: blend 3m and 6m simple returns.
    ret_short = (
        last_close / float(close.iloc[-_MOM_SHORT]) - 1
        if len(close) > _MOM_SHORT
        else 0.0
    )
    ret_long = (
        last_close / float(close.iloc[-_MOM_LONG]) - 1
        if len(close) > _MOM_LONG
        else ret_short
    )
    momentum = 0.5 * ret_short + 0.5 * ret_long

    # RSI(14) for the setup score.
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = (
        float((100 - 100 / (1 + rs)).iloc[-1]) if not math.isnan(rs.iloc[-1]) else 50.0
    )

    # Extension above EMA20 (how stretched / how much room).
    ext_from_ema20 = (
        (last_close - ema20.iloc[-1]) / ema20.iloc[-1] if ema20.iloc[-1] else 0.0
    )

    return {
        "symbol": symbol,
        "last_close": round(last_close, 2),
        "avg_turnover_cr": round(avg_turnover_cr, 2),
        "avg_volume_30d": int(avg_volume_30d),
        "ret_3m_pct": round(ret_short * 100, 2),
        "ret_6m_pct": round(ret_long * 100, 2),
        "momentum": momentum,
        "ema50_slope": ema50_slope,
        "trend_stacked": bool(stacked),
        "rsi": round(rsi, 1),
        "ext_from_ema20": ext_from_ema20,
    }


def _scale(series: pd.Series) -> pd.Series:
    """Min-max scale to 0-1; constant series -> 0.5."""
    lo, hi = series.min(), series.max()
    if hi - lo < 1e-9:
        return pd.Series(0.5, index=series.index)
    return (series - lo) / (hi - lo)


def _score(rows: List[Dict]) -> pd.DataFrame:
    """Attach a 0-100 rank score to each candidate row."""
    df = pd.DataFrame(rows)

    # Liquidity: log turnover so a ₹1000 Cr name doesn't dwarf everything.
    liquidity = _scale(np.log1p(df["avg_turnover_cr"]))

    # Trend: EMA50 slope, bonus for a clean stack.
    trend = _scale(df["ema50_slope"]) * 0.7 + df["trend_stacked"].astype(float) * 0.3

    momentum = _scale(df["momentum"])

    # Relative strength: 6m return vs pool median.
    median_ret = df["ret_6m_pct"].median()
    rel_strength = _scale(df["ret_6m_pct"] - median_ret)

    # Setup: reward RSI in 45-70, penalise overextension from EMA20.
    rsi_fit = 1 - (df["rsi"] - 57.5).abs() / 57.5
    rsi_fit = rsi_fit.clip(lower=0)
    ext_penalty = (df["ext_from_ema20"].clip(lower=0) / 0.15).clip(upper=1)
    setup = (rsi_fit * 0.7 + (1 - ext_penalty) * 0.3).clip(lower=0)

    df["score"] = (
        liquidity * 25 + trend * 25 + momentum * 25 + rel_strength * 15 + setup * 10
    ).round(2)
    df["segment"] = df["avg_turnover_cr"].map(_segment_for_turnover)
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rebuild seed_universe.csv from ranked OHLCV."
    )
    ap.add_argument(
        "--add", type=Path, default=None, help="extra candidate CSV (col: symbol)"
    )
    ap.add_argument("--top", type=int, default=500, help="keep top-N ranked symbols")
    ap.add_argument(
        "--report", type=Path, default=Path("plutus/data/universe_ranked.csv")
    )
    ap.add_argument("--min-bars", type=int, default=150)
    ap.add_argument(
        "--dry-run", action="store_true", help="do not overwrite seed_universe.csv"
    )
    args = ap.parse_args()

    seed_csv = Path(settings.UNIVERSE_SEED_CSV)
    pool = _load_candidate_pool(seed_csv, args.add)
    if not pool:
        logger.error("Empty candidate pool. Is %s present?", seed_csv)
        return 1
    logger.info("Candidate pool: %d symbols", len(pool))

    rows: List[Dict] = []
    failed = 0
    for i, symbol in enumerate(pool, 1):
        try:
            df = fetch_ohlcv(symbol, days=max(args.min_bars + 60, 260), interval="1d")
        except Exception as e:
            logger.debug("fetch failed for %s: %s", symbol, e)
            failed += 1
            continue
        if df is None or len(df) < args.min_bars:
            failed += 1
            continue
        metrics = _compute_metrics(symbol, df)
        if metrics:
            rows.append(metrics)
        if i % 50 == 0:
            logger.info("  processed %d/%d (kept %d)", i, len(pool), len(rows))

    if not rows:
        logger.error("No symbols passed the hard gates. Nothing to write.")
        return 1

    ranked = _score(rows)
    logger.info(
        "Passed gates: %d / %d  (fetch/short failures: %d)",
        len(ranked),
        len(pool),
        failed,
    )

    # Full ranked report (all metrics) — always written.
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report_cols = [
        "symbol",
        "score",
        "segment",
        "last_close",
        "avg_turnover_cr",
        "avg_volume_30d",
        "ret_3m_pct",
        "ret_6m_pct",
        "rsi",
        "trend_stacked",
    ]
    ranked[report_cols].to_csv(args.report, index=False)
    logger.info("Wrote ranked report -> %s", args.report)

    top = ranked.head(args.top)
    seg_counts = top["segment"].value_counts().to_dict()
    logger.info("Top %d segment mix: %s", len(top), seg_counts)
    logger.info(
        "Top 10 by score:\n%s",
        top[["symbol", "score", "segment", "ret_6m_pct"]]
        .head(10)
        .to_string(index=False),
    )

    if args.dry_run:
        logger.info("--dry-run: seed_universe.csv left unchanged.")
        return 0

    # Overwrite seed CSV with the same schema the loader expects.
    out = top[["symbol", "segment"]].copy()
    out.insert(1, "exchange", "NSE")
    out.to_csv(seed_csv, index=False)
    logger.info(
        "Wrote %d symbols -> %s (was the candidate pool of %d)",
        len(out),
        seed_csv,
        len(pool),
    )
    logger.info("Generated %s", date.today().isoformat())
    return 0


if __name__ == "__main__":
    sys.exit(main())
