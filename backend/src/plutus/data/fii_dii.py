from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd

_ROLLING_WINDOW = 5


class FlowsProvider(Protocol):
    def fetch(self, start: date, end: date) -> pd.DataFrame: ...


def fetch_flows(start: date, end: date, provider: FlowsProvider) -> pd.DataFrame:
    """Daily net FII/DII flows in ₹ crore, separate columns (A7 data side, B13).

    Columns: fii_net_inr_crore, dii_net_inr_crore.
    """
    return provider.fetch(start, end)


def rolling_net_flow_5d(net_flow: pd.Series) -> pd.Series:
    """5-day rolling sum of net flows; consumed by shared/regime (A7)."""
    return net_flow.rolling(_ROLLING_WINDOW, min_periods=1).sum()
