from __future__ import annotations

from datetime import date

import pandas as pd


class RegimeSwitched:
    def equity_curve(
        self,
        start: date,
        end: date,
        nifty_closes: pd.Series,
        regime_history: pd.Series,
    ) -> pd.Series:
        closes = nifty_closes.loc[pd.Timestamp(start) : pd.Timestamp(end)]
        regimes = regime_history.reindex(closes.index)
        daily_returns = closes.pct_change().fillna(0.0)
        # long Nifty when prior day's label is BULL; flat (cash) otherwise
        prior_bull = regimes.shift(1).eq("BULL")
        captured = daily_returns.where(prior_bull, 0.0)
        return (1.0 + captured).cumprod()
