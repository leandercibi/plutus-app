from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plutus.shared.types import BundleSignal


@dataclass(frozen=True)
class BundleRegimeStat:
    """Selector's read view of a per-regime bundle stat (A2). Mirrors the
    db.BundleStatPerRegime columns the selector needs, decoupled from the ORM."""

    bundle: str
    regime: str
    oos_sharpe_shrunk: float
    n_trades: int


@dataclass(frozen=True)
class SelectorInputs:
    pooled_oos_stats: dict[tuple[str, str], BundleRegimeStat]
    min_n: int = 20
    composite_top_quartile_only: bool = True
    decisive_delta: float = 0.3


class BundleSelector:
    """A2 — rank by walk-forward OOS per-regime shrunk Sharpe.
    A11 — default seeding favours Composite when it ranks in the top quartile."""

    def __init__(self, inputs: SelectorInputs) -> None:
        self._inputs = inputs

    def rank_bundles(self, regime: str, candidates: list[BundleSignal]) -> list[BundleSignal]:
        eligible: list[tuple[float, BundleSignal]] = []
        for sig in candidates:
            stat = self._inputs.pooled_oos_stats.get((sig.bundle, regime))
            if stat is None or stat.n_trades < self._inputs.min_n:
                continue
            eligible.append((stat.oos_sharpe_shrunk, sig))

        if not eligible:
            return []

        eligible.sort(key=lambda pair: pair[0], reverse=True)
        ranked = [sig for _, sig in eligible]

        seeded = self._default_seed(regime, eligible)
        if seeded is not None:
            ranked = [seeded] + [s for s in ranked if s is not seeded]
        return ranked

    def _default_seed(
        self, regime: str, eligible: list[tuple[float, BundleSignal]]
    ) -> BundleSignal | None:
        composite = next((sig for _, sig in eligible if sig.bundle == "composite"), None)
        if composite is not None:
            sharpes = [sharpe for sharpe, _ in eligible]
            top_quartile_floor = float(np.percentile(sharpes, 75, method="lower"))
            composite_sharpe = next(sharpe for sharpe, sig in eligible if sig.bundle == "composite")
            if composite_sharpe >= top_quartile_floor:
                return composite

        # else: single best bundle, only if decisively better than runner-up
        if len(eligible) == 1:
            return eligible[0][1]
        best_sharpe, best_sig = eligible[0]
        second_sharpe = eligible[1][0]
        if best_sharpe - second_sharpe >= self._inputs.decisive_delta:
            return best_sig
        return None
