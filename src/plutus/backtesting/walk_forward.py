from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from plutus.backtesting.pooled import stats_from_trades
from plutus.shared.types import BacktestTrade, BundleStats


@dataclass(frozen=True)
class Window:
    start: date
    end: date


class WalkForward:
    def windows(
        self,
        start: date,
        end: date,
        train_days: int = 180,
        oos_days: int = 30,
        step_days: int = 30,
    ) -> Iterator[tuple[Window, Window]]:
        train_start = start
        while True:
            train_end = train_start + timedelta(days=train_days)
            oos_start = train_end
            oos_end = oos_start + timedelta(days=oos_days)
            if oos_end > end:
                break
            yield Window(train_start, train_end), Window(oos_start, oos_end)
            train_start = train_start + timedelta(days=step_days)

    def stats(self, trades: list[BacktestTrade], window: Window) -> BundleStats:
        in_window = [t for t in trades if window.start <= t.entry_date < window.end]
        bundle = in_window[0].bundle if in_window else "ALL"
        return stats_from_trades(in_window, bundle=bundle, regime="ALL")
