from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from plutus.shared.types import BacktestTrade


@dataclass(frozen=True)
class BenchmarkResult:
    plutus_net_pct: float
    nifty_net_pct: float
    regime_switched_net_pct: float
    random_liquid_net_pct: float
    plutus_profit_factor: float
    plutus_n_trades: int


def _net_pct(curve: pd.Series) -> float:
    return float(curve.iloc[-1] / curve.iloc[0] - 1.0) * 100.0


def _profit_factor(trades: list[BacktestTrade]) -> float:
    gains = sum(t.realized_R for t in trades if t.realized_R > 0)
    losses = sum(t.realized_R for t in trades if t.realized_R < 0)
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / abs(losses))


class BenchmarkStrip:
    def compute(
        self,
        plutus_trades: list[BacktestTrade],
        plutus_curve: pd.Series,
        nifty_curve: pd.Series,
        regime_curve: pd.Series,
        random_curve: pd.Series,
    ) -> BenchmarkResult:
        return BenchmarkResult(
            plutus_net_pct=_net_pct(plutus_curve),
            nifty_net_pct=_net_pct(nifty_curve),
            regime_switched_net_pct=_net_pct(regime_curve),
            random_liquid_net_pct=_net_pct(random_curve),
            plutus_profit_factor=_profit_factor(plutus_trades),
            plutus_n_trades=len(plutus_trades),
        )
