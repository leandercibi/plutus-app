from __future__ import annotations

import logging
from datetime import date
from io import StringIO

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_URL_TEMPLATE = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"


class NseDeliveryProvider:
    """Fetches NSE's daily "Security-wise Delivery Position" bhavcopy CSV.

    One file per trading day, all NSE-listed symbols. Not published on weekends/
    market holidays — callers should treat a missing day as "no data," not an error.
    """

    def fetch_day(self, as_of: date) -> pd.DataFrame:
        """Return columns: symbol, delivery_qty, traded_qty, delivery_pct (fractional).

        Empty DataFrame (not an exception) if the day has no published bhavcopy
        (weekend/holiday) or the fetch/parse fails.
        """
        url = _URL_TEMPLATE.format(date=as_of.strftime("%d%m%Y"))
        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Referer": "https://www.nseindia.com/all-reports",
                },
                timeout=20,
            )
            if resp.status_code != 200 or len(resp.content) < 100:
                logger.info("no bhavcopy for %s (status=%d)", as_of, resp.status_code)
                return _empty()
            df = pd.read_csv(StringIO(resp.text))
        except Exception:
            logger.warning("bhavcopy fetch failed for %s", as_of, exc_info=True)
            return _empty()

        df.columns = [c.strip() for c in df.columns]
        required = {"SYMBOL", "SERIES", "TTL_TRD_QNTY", "DELIV_QTY", "DELIV_PER"}
        if not required.issubset(df.columns):
            logger.warning(
                "bhavcopy for %s missing expected columns: %s", as_of, df.columns.tolist()
            )
            return _empty()

        for col in ("SYMBOL", "SERIES"):
            df[col] = df[col].astype(str).str.strip()
        df = df[df["SERIES"] == "EQ"].copy()

        out = pd.DataFrame(
            {
                "symbol": df["SYMBOL"],
                "delivery_qty": pd.to_numeric(df["DELIV_QTY"], errors="coerce")
                .fillna(0)
                .astype(int),
                "traded_qty": pd.to_numeric(df["TTL_TRD_QNTY"], errors="coerce")
                .fillna(0)
                .astype(int),
                "delivery_pct": (pd.to_numeric(df["DELIV_PER"], errors="coerce") / 100.0).fillna(
                    0.0
                ),
            }
        )
        return out.dropna(subset=["symbol"]).reset_index(drop=True)


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["symbol", "delivery_qty", "traded_qty", "delivery_pct"])
