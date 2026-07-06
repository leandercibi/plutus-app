#!/usr/bin/env python3
"""Refresh scripts/nse500.csv from NSE India's Nifty 500 constituent list.

Run this periodically (e.g. once a month) to keep the universe up to date:
    python scripts/refresh_nse_universe.py
"""

from __future__ import annotations

import csv
import io
import ssl
import sys
import urllib.request
from pathlib import Path

_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
_OUT = Path(__file__).parent / "nse500.csv"


def fetch_nifty500() -> list[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        )
    }
    req = urllib.request.Request(_URL, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        data = resp.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(data))
    return sorted(row["Symbol"].strip() for row in reader if row.get("Symbol", "").strip())


def write_csv(symbols: list[str]) -> None:
    with open(_OUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol"])
        for sym in symbols:
            writer.writerow([sym])


def main() -> None:
    print("Fetching Nifty 500 list from NSE India…")
    try:
        symbols = fetch_nifty500()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    write_csv(symbols)
    print(f"Wrote {len(symbols)} symbols → {_OUT}")


if __name__ == "__main__":
    main()
