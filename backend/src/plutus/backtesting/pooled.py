from __future__ import annotations

import math
from typing import Literal

from plutus.config.settings import get_settings
from plutus.shared.types import BacktestTrade, BundleStats

GroupKey = Literal["bundle", "regime"]

# A3 guard: pooling is ONLY ever by bundle and/or regime — never by symbol.
_GROUP_KEYS_DOC = "bundle, regime"

_CI_Z = 1.96


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _std(values: list[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def stats_from_trades(
    trades: list[BacktestTrade], bundle: str, regime: str | Literal["ALL"]
) -> BundleStats:
    n = len(trades)
    if n == 0:
        return BundleStats(
            bundle=bundle,
            regime=regime,
            n_trades=0,
            win_rate=0.0,
            expectancy_R=0.0,
            sharpe_raw=0.0,
            ci_low_R=0.0,
            ci_high_R=0.0,
        )
    rs = [t.realized_R for t in trades]
    mean = _mean(rs)
    std = _std(rs, mean)
    win_rate = sum(1 for r in rs if r > 0) / n
    sharpe_raw = mean / std if std > 0 else 0.0
    half = _CI_Z * std / math.sqrt(n) if std > 0 else 0.0
    return BundleStats(
        bundle=bundle,
        regime=regime,
        n_trades=n,
        win_rate=win_rate,
        expectancy_R=mean,
        sharpe_raw=sharpe_raw,
        ci_low_R=mean - half,
        ci_high_R=mean + half,
    )


class PooledStats:
    def compute(
        self, trades: list[BacktestTrade], group_by: list[GroupKey]
    ) -> dict[object, BundleStats]:
        """Pool across the universe per bundle and/or per (bundle, regime).

        Never groups by symbol (A3). Returns a string key when grouping by bundle
        alone, otherwise a tuple key in group_by order.
        """
        groups: dict[object, list[BacktestTrade]] = {}
        for t in trades:
            key = self._key(t, group_by)
            groups.setdefault(key, []).append(t)

        out: dict[object, BundleStats] = {}
        for key, group_trades in groups.items():
            bundle = group_trades[0].bundle
            regime = self._regime_of(key, group_by, group_trades[0])
            out[key] = stats_from_trades(group_trades, bundle=bundle, regime=regime)
        return out

    def eligible_for_ranking(
        self, stats: dict[object, BundleStats]
    ) -> dict[object, BundleStats]:
        min_n = get_settings().bundle_min_n
        return {k: s for k, s in stats.items() if s.n_trades >= min_n}

    @staticmethod
    def _key(trade: BacktestTrade, group_by: list[GroupKey]) -> object:
        parts = tuple(getattr(trade, g) for g in group_by)
        return parts[0] if len(parts) == 1 else parts

    @staticmethod
    def _regime_of(key: object, group_by: list[GroupKey], sample: BacktestTrade) -> str:
        if "regime" in group_by:
            return sample.regime
        return "ALL"
