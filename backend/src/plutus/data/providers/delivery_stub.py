from __future__ import annotations

import hashlib
from datetime import date

import numpy as np
import pandas as pd


class DeliveryStubProvider:
    """Synthetic delivery data based on volume.

    NSE bhav copy delivery data isn't available via public APIs.
    This stub produces delivery_pct in [0.35, 0.65] seeded by symbol for
    reproducibility. Replace with real NSE bhav copy adapter in prod.
    """

    name: str = "delivery_stub"

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        raise NotImplementedError(
            "DeliveryStubProvider.fetch is called via annotate_delivery; "
            "pass a candles DataFrame to annotate_delivery instead."
        )

    def annotate_delivery(self, symbol: str, candles: pd.DataFrame) -> pd.DataFrame:
        """Add delivery columns to an existing OHLCV DataFrame."""
        seed = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16) % (2**31)
        rng = np.random.default_rng(seed)
        n = len(candles)
        volume = candles["volume"].astype(float).values
        pct = rng.uniform(0.35, 0.65, n)
        df = candles.copy()
        df["delivery_qty"] = (volume * pct).astype(int)
        df["traded_qty"] = volume.astype(int)
        df["delivery_pct"] = pct
        return df
