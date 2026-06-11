# src/plutus/data/refresh_universe.py
"""
Weekly universe refresh using NSE bhav copy + Angel One bulk market data.

Strategy to minimise API calls:
  1. Download NSE bhav copy (single ZIP → single CSV) — covers ALL ~2000 listed stocks.
     Zero Angel One calls needed for price/volume screening.
  2. Apply fundamental-style filters on bhav copy data (price, delivery%, turnover).
  3. Optionally enrich top candidates with Angel One getCandleData for 52W high/ATR
     (batched, max 50 calls per run if needed).
  4. Write seed_universe_v2.csv with the surviving symbols.

Run this every Sunday at ~6 PM (already wired in config: WEEKLY_RUN_DAY/HOUR).

Usage:
    python -m plutus.data.refresh_universe          # dry-run, prints survivors
    python -m plutus.data.refresh_universe --write  # overwrites seed_universe_v2.csv
"""

import argparse
import io
import logging
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from plutus.config import settings

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

NSE_BHAV_URL = (
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"
)
NSE_BHAV_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}

SEED_CSV_V2 = Path("src/plutus/data/seed_universe_v2.csv")

# Filters — tweak via .env or edit directly
PRICE_MIN: float = 50.0
PRICE_MAX: float = 10_000.0
MIN_TURNOVER_CR: float = 5.0  # avg daily turnover in crores
MIN_DELIVERY_PCT: float = 25.0  # delivery % (filters out pure speculative)
MAX_SYMBOLS: int = 500


# ── NSE bhav copy ────────────────────────────────────────────────────────────


def _last_trading_date() -> date:
    """Return most recent weekday (simple heuristic; does not skip NSE holidays)."""
    d = date.today()
    while d.weekday() >= 5:  # Saturday=5, Sunday=6
        d -= timedelta(days=1)
    return d


def fetch_bhav_copy(trading_date: date | None = None) -> pd.DataFrame:
    """
    Download NSE full bhav copy for `trading_date` (defaults to last trading day).
    Returns DataFrame with columns: SYMBOL, CLOSE_PRICE, TURNOVER_LACS, DELIV_PER
    plus raw columns for further filtering.

    Single HTTP request — no per-symbol API calls.
    """
    trading_date = trading_date or _last_trading_date()
    url = NSE_BHAV_URL.format(date=trading_date.strftime("%d%m%Y"))

    logger.info("Fetching NSE bhav copy for %s …", trading_date)
    resp = requests.get(url, headers=NSE_BHAV_HEADERS, timeout=30)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = df.columns.str.strip()

    # Keep EQ series only (exclude BE, SM, etc.)
    if "SERIES" in df.columns:
        df = df[df["SERIES"].str.strip() == "EQ"]

    # Normalise column names across bhav copy variants
    col_map = {
        "SYMBOL": "SYMBOL",
        "CLOSE_PRICE": "CLOSE",
        "LAST_PRICE": "CLOSE",
        "ClosePrice": "CLOSE",
        "TURNOVER_LACS": "TURNOVER_LACS",
        "Turnover": "TURNOVER_LACS",
        "DELIV_PER": "DELIV_PER",
        "% Dly Qt to Traded Qty": "DELIV_PER",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    required = {"SYMBOL", "CLOSE", "TURNOVER_LACS"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Bhav copy missing expected columns: {missing}. Got: {list(df.columns)}"
        )

    df["SYMBOL"] = df["SYMBOL"].str.strip().str.upper()
    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
    df["TURNOVER_LACS"] = pd.to_numeric(df["TURNOVER_LACS"], errors="coerce")
    if "DELIV_PER" in df.columns:
        df["DELIV_PER"] = pd.to_numeric(df["DELIV_PER"], errors="coerce")
    else:
        df["DELIV_PER"] = 100.0  # unknown → don't penalise

    return df.dropna(subset=["SYMBOL", "CLOSE", "TURNOVER_LACS"])


# ── Filtering ─────────────────────────────────────────────────────────────────


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply price, turnover, and delivery % filters to bhav copy DataFrame."""
    turnover_cr = df["TURNOVER_LACS"] / 100.0  # lacs → crores

    mask = (
        df["CLOSE"].between(PRICE_MIN, PRICE_MAX)
        & (turnover_cr >= MIN_TURNOVER_CR)
        & (df["DELIV_PER"] >= MIN_DELIVERY_PCT)
    )
    filtered = df[mask].copy()
    filtered["TURNOVER_CR"] = turnover_cr[mask]

    # Sort: higher turnover first (more liquid = better for swing)
    filtered = filtered.sort_values("TURNOVER_CR", ascending=False)
    logger.info("Bhav copy: %d EQ stocks → %d after filters", len(df), len(filtered))
    return filtered


# ── Optional: Angel One 52W high enrichment (max 50 calls) ──────────────────


def _angel_52w_high(symbols: list[str]) -> dict[str, float]:
    """
    Fetch 252-day high for each symbol via Angel One getCandleData.
    Used to score 52W-high proximity (momentum proxy).
    Batches up to 50 symbols to stay within rate limits (~18 sec total).
    Returns {symbol: high_52w} dict; missing symbols are excluded.
    """
    from plutus.data.ohlcv import _angel_session, _angel_symbol_token, _bare_symbol

    if not (settings.ANGEL_API_KEY and settings.ANGEL_CLIENT_ID):
        logger.info("Angel One credentials not set — skipping 52W high enrichment")
        return {}

    obj = _angel_session()
    result: dict[str, float] = {}

    for sym in symbols[:50]:  # hard cap at 50 API calls per refresh
        bare = _bare_symbol(sym)
        token = _angel_symbol_token(bare)
        if not token:
            continue
        try:
            from datetime import datetime

            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=262)
            data = obj.getCandleData(
                {
                    "exchange": "NSE",
                    "symboltoken": token,
                    "interval": "ONE_DAY",
                    "fromdate": start_dt.strftime("%Y-%m-%d 09:00"),
                    "todate": end_dt.strftime("%Y-%m-%d 15:30"),
                }
            )
            if data.get("data"):
                highs = [row[2] for row in data["data"]]  # index 2 = High
                result[sym] = max(highs)
            time.sleep(0.35)  # 3 req/sec cap
        except Exception as e:
            logger.debug("52W high fetch failed for %s: %s", sym, e)

    return result


# ── Segment classifier ────────────────────────────────────────────────────────


def _classify_segment(turnover_cr: float, close: float) -> str:
    """Heuristic segment based on liquidity and price (refine as needed)."""
    if turnover_cr >= 50:
        return "LARGE_CAP"
    elif turnover_cr >= 10:
        return "MID_CAP"
    else:
        return "SMALL_CAP"


# ── Main refresh logic ────────────────────────────────────────────────────────


def build_universe(
    trading_date: date | None = None,
    enrich_with_angel: bool = False,
) -> pd.DataFrame:
    """
    Full pipeline: bhav copy → filter → optional Angel One 52W enrichment → top N.
    Returns DataFrame with columns: symbol, exchange, segment.
    """
    bhav = fetch_bhav_copy(trading_date)
    filtered = apply_filters(bhav)

    if enrich_with_angel and len(filtered) > 0:
        top_symbols = filtered["SYMBOL"].tolist()[:50]
        high_map = _angel_52w_high(top_symbols)
        if high_map:
            # Score: proximity to 52W high (higher = better momentum)
            filtered["HIGH_52W"] = filtered["SYMBOL"].map(high_map)
            filtered["PCT_FROM_HIGH"] = (
                (filtered["HIGH_52W"] - filtered["CLOSE"]) / filtered["HIGH_52W"] * 100
            ).fillna(999)
            # Re-sort: within top turnover tier, prefer near 52W high
            filtered = filtered.sort_values(
                ["TURNOVER_CR", "PCT_FROM_HIGH"], ascending=[False, True]
            )

    top = filtered.head(MAX_SYMBOLS).copy()
    top["segment"] = top.apply(
        lambda r: _classify_segment(r["TURNOVER_CR"], r["CLOSE"]), axis=1
    )
    result = top[["SYMBOL", "segment"]].rename(columns={"SYMBOL": "symbol"})
    result["exchange"] = "NSE"
    result = result[["symbol", "exchange", "segment"]].reset_index(drop=True)
    return result


def write_universe(df: pd.DataFrame, path: Path = SEED_CSV_V2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logger.info("Wrote %d symbols to %s", len(df), path)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Refresh seed universe CSV from NSE bhav copy"
    )
    parser.add_argument(
        "--write", action="store_true", help="Overwrite seed_universe_v2.csv"
    )
    parser.add_argument(
        "--angel",
        action="store_true",
        help="Enrich with Angel One 52W high (uses up to 50 API calls)",
    )
    parser.add_argument(
        "--date", help="Trading date YYYY-MM-DD (default: last trading day)"
    )
    args = parser.parse_args()

    trading_date = date.fromisoformat(args.date) if args.date else None
    universe = build_universe(trading_date=trading_date, enrich_with_angel=args.angel)

    print(f"\nTop 10 by liquidity:\n{universe.head(10).to_string(index=False)}")
    print(f"\nTotal: {len(universe)} symbols")
    print(f"Segments: {universe['segment'].value_counts().to_dict()}")

    if args.write:
        write_universe(universe)
        print(f"\nWritten to {SEED_CSV_V2}")
    else:
        print("\nDry-run. Pass --write to save.")
