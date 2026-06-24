from __future__ import annotations

from plutus.backtesting.shrinkage import shrunk_sharpe


def test_low_n_pulled_toward_prior_mean() -> None:
    # With n=1 and prior_weight=30, shrinkage ~= 30/31, so result hugs prior_mean.
    raw = 2.0
    prior_mean = 0.0
    result = shrunk_sharpe(raw, n_trades=1, prior_mean=prior_mean, prior_weight=30.0)
    assert abs(result - prior_mean) < abs(result - raw)


def test_high_n_close_to_raw() -> None:
    # With n=3000 and prior_weight=30, shrinkage ~= 30/3030, so result hugs raw.
    raw = 2.0
    prior_mean = 0.0
    result = shrunk_sharpe(raw, n_trades=3000, prior_mean=prior_mean, prior_weight=30.0)
    assert abs(result - raw) < abs(result - prior_mean)


def test_formula_exact() -> None:
    raw = 1.5
    prior_mean = 0.5
    n = 30
    prior_weight = 30.0
    # shrinkage = 30/60 = 0.5 -> 1.5*0.5 + 0.5*0.5 = 1.0
    result = shrunk_sharpe(
        raw, n_trades=n, prior_mean=prior_mean, prior_weight=prior_weight
    )
    assert result == 1.0


def test_zero_trades_returns_prior_mean() -> None:
    # n=0 -> shrinkage = 30/30 = 1.0 -> all prior_mean.
    result = shrunk_sharpe(2.0, n_trades=0, prior_mean=0.3, prior_weight=30.0)
    assert result == 0.3
