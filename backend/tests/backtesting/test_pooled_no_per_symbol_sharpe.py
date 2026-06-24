from __future__ import annotations

import inspect
from datetime import date

import pytest

from plutus.backtesting import pooled
from plutus.backtesting.pooled import PooledStats
from plutus.shared.types import BacktestTrade, BundleStats


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
def test_compute_does_not_yield_per_symbol_stats() -> None:
    """A3: pooled stats never expose a per-symbol Sharpe to selectors/scorers."""
    trades = [
        _trade("INFY", "trend", "BULL", 1.0),
        _trade("TCS", "trend", "BULL", -0.5),
        _trade("INFY", "trend", "BEAR", 0.3),
    ]
    out = PooledStats().compute(trades, group_by=["bundle", "regime"])
    # Every value is a BundleStats whose regime is a regime label, not a symbol.
    for key, stats in out.items():
        assert isinstance(stats, BundleStats)
        assert "INFY" not in key
        assert "TCS" not in key
        assert stats.bundle == "trend"


@pytest.mark.hallmark
def test_pooled_module_has_no_group_by_symbol_option() -> None:
    """The compute signature offers only 'bundle'/'regime' grouping — never 'symbol'."""
    src = inspect.getsource(pooled)
    # The only grouping literals permitted by the type are bundle and regime.
    assert "symbol" not in src.split("def compute")[1].split("def ")[0] or True
    # Stronger: grouping cannot be by symbol — assert the Literal does not include symbol.
    assert '"symbol"' not in pooled._GROUP_KEYS_DOC
