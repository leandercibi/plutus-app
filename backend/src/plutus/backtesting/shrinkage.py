from __future__ import annotations


def shrunk_sharpe(
    raw_sharpe: float, n_trades: int, prior_mean: float, prior_weight: float = 30.0
) -> float:
    """James-Stein-style shrinkage of a raw Sharpe toward a cross-bundle prior.

    Lower n -> pulled toward prior_mean; higher n -> close to raw.
    """
    shrinkage = prior_weight / (prior_weight + n_trades)
    return raw_sharpe * (1 - shrinkage) + prior_mean * shrinkage
