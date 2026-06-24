from __future__ import annotations

from datetime import date
from typing import cast

import pandas as pd


class NiftyBuyHold:
    def equity_curve(
        self, start: date, end: date, nifty_closes: pd.Series
    ) -> pd.Series:
        window = nifty_closes.loc[pd.Timestamp(start) : pd.Timestamp(end)]
        return cast("pd.Series", window / window.iloc[0])
