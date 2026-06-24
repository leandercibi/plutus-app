from __future__ import annotations

from datetime import date

import pytest

from plutus.backtesting.pooled import PooledStats
from plutus.shared.types import BacktestTrade


def _trade(symbol: str, bundle: str, regime: str, r: float) -> BacktestTrade:
    return BacktestTrade(
        symbol=symbol,
        bundle=bundle,
        regime=regime,
        entry_date=date(2020, 1, 1),
        exit_date=date(2020, 1, 10),
        realized_R=r,
        hold_days=9,
    )


@pytest.mark.hallmark
def test_compute_keys_are_never_per_symbol() -> None:
    """A3 hallmark: PooledStats.compute keys are bundle or (bundle, regime), never symbols."""
    trades = [
        _trade("INFY", "trend", "BULL", 1.0),
        _trade("TCS", "trend", "BULL", -0.5),
        _trade("HDFC", "breakout", "BEAR", 0.8),
    ]
    by_bundle = PooledStats().compute(trades, group_by=["bundle"])
    by_bundle_regime = PooledStats().compute(trades, group_by=["bundle", "regime"])

    symbols = {"INFY", "TCS", "HDFC"}
    # No key (or component of a tuple key) is a symbol.
    for key in by_bundle:
        assert key not in symbols
    for key in by_bundle_regime:
        assert isinstance(key, tuple)
        for component in key:
            assert component not in symbols
    # bundle grouping keys are bundle names
    assert set(by_bundle.keys()) == {"trend", "breakout"}
    assert set(by_bundle_regime.keys()) == {("trend", "BULL"), ("breakout", "BEAR")}


def test_expectancy_and_win_rate() -> None:
    trades = [
        _trade("A", "trend", "BULL", 2.0),
        _trade("B", "trend", "BULL", 0.0),
        _trade("C", "trend", "BULL", -1.0),
    ]
    stats = PooledStats().compute(trades, group_by=["bundle"])["trend"]
    assert stats.n_trades == 3
    # expectancy = mean of (2, 0, -1) = 1/3
    assert stats.expectancy_R == pytest.approx(1.0 / 3.0)
    # win_rate = fraction realized_R > 0 = 1/3
    assert stats.win_rate == pytest.approx(1.0 / 3.0)


def test_sharpe_zero_when_no_variance() -> None:
    trades = [_trade("A", "trend", "BULL", 1.0), _trade("B", "trend", "BULL", 1.0)]
    stats = PooledStats().compute(trades, group_by=["bundle"])["trend"]
    assert stats.sharpe_raw == 0.0


def test_eligible_for_ranking_floor() -> None:
    """Bundles with n < settings.bundle_min_n (20) excluded from ranking-eligible set."""
    few = [_trade(f"S{i}", "trend", "BULL", 1.0) for i in range(5)]
    many = [_trade(f"T{i}", "breakout", "BULL", 1.0) for i in range(25)]
    pooled = PooledStats()
    all_stats = pooled.compute(few + many, group_by=["bundle"])
    eligible = pooled.eligible_for_ranking(all_stats)
    # both computed
    assert set(all_stats.keys()) == {"trend", "breakout"}
    # only the n>=20 bundle is ranking-eligible
    assert "breakout" in eligible
    assert "trend" not in eligible
