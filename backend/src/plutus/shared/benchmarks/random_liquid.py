from __future__ import annotations

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd

from plutus.shared.types import BacktestTrade


class RandomLiquidBaseline:
    def __init__(self, seed: int = 42) -> None:
        self._seed = seed

    def matched_picks(
        self,
        plutus_trades: list[BacktestTrade],
        universe_at: Callable[[date], frozenset[str]],
    ) -> list[tuple[BacktestTrade, str, int]]:
        rng = np.random.default_rng(self._seed)
        picks: list[tuple[BacktestTrade, str, int]] = []
        for trade in plutus_trades:
            candidates = sorted(universe_at(trade.entry_date))
            chosen = candidates[int(rng.integers(0, len(candidates)))]
            picks.append((trade, chosen, trade.hold_days))
        return picks

    def matched_trade_curve(
        self,
        plutus_trades: list[BacktestTrade],
        universe_at: Callable[[date], frozenset[str]],
        returns_for: Callable[[str, date, int], float],
    ) -> pd.Series:
        picks = self.matched_picks(plutus_trades, universe_at)
        equity = 1.0
        values = [equity]
        index: list[date] = (
            [plutus_trades[0].entry_date] if plutus_trades else [date.min]
        )
        for trade, symbol, hold_days in picks:
            equity *= 1.0 + returns_for(symbol, trade.entry_date, hold_days)
            values.append(equity)
            index.append(trade.exit_date)
        return pd.Series(values, index=pd.to_datetime(index))
