from __future__ import annotations

import calendar
from datetime import date, timedelta

import pandas as pd

from plutus.data.base import DeliveryProvider

_THURSDAY = 3


def fetch_delivery(symbol: str, start: date, end: date, provider: DeliveryProvider) -> pd.DataFrame:
    """Normalize delivery data: delivery_pct = delivery_qty / traded_qty, clipped [0,1].

    Missing days yield NaN delivery_pct (never silently zero).
    """
    df = provider.fetch(symbol, start, end).copy()
    delivery_qty = df["delivery_qty"].astype(float)
    traded_qty = df["traded_qty"].astype(float)
    pct = delivery_qty / traded_qty
    df["delivery_pct"] = pct.clip(lower=0.0, upper=1.0)
    return df


def delivery_adjusted_volume(traded_qty: pd.Series, delivery_pct: pd.Series) -> pd.Series:
    """Replace raw volume in confirmation gates with delivery-weighted volume (A9)."""
    return traded_qty.astype(float) * delivery_pct.astype(float)


def _last_thursday(year: int, month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    while d.weekday() != _THURSDAY:
        d -= timedelta(days=1)
    return d


def is_expiry_or_rebalance_day(d: date) -> bool:
    """F&O monthly expiry (last Thursday) — volume is untrustworthy that day (A9)."""
    return d == _last_thursday(d.year, d.month)
