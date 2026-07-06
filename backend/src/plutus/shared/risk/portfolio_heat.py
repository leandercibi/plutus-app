from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.risk.types import OpenPosition


class _Proposable(Protocol):
    symbol: str
    sector: str
    risk_R: float


@dataclass(frozen=True)
class HeatInputs:
    open_positions: list[OpenPosition]
    proposed: _Proposable
    pairwise_correlations: pd.DataFrame


@dataclass(frozen=True)
class HeatDecision:
    allowed: bool
    current_heat_R: float
    projected_heat_R: float
    reasons: list[str] = field(default_factory=list)


def _as_float(value: Any) -> float:
    return float(value)


def _heat_with_haircut(
    symbols: list[str],
    risks: dict[str, float],
    corr: pd.DataFrame,
) -> float:
    total = 0.0
    for sym in symbols:
        others = [s for s in symbols if s != sym]
        if others:
            corr_values = [_as_float(corr.loc[sym, o]) for o in others]
            mean_corr = sum(corr_values) / len(corr_values)
        else:
            mean_corr = 0.0
        total += risks[sym] * (1.0 + mean_corr)
    return total


class PortfolioHeat:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(self, inputs: HeatInputs) -> HeatDecision:
        open_syms = [p.symbol for p in inputs.open_positions]
        open_risks = {p.symbol: p.risk_R for p in inputs.open_positions}
        current = _heat_with_haircut(open_syms, open_risks, inputs.pairwise_correlations)

        proj_syms = [*open_syms, inputs.proposed.symbol]
        proj_risks = {**open_risks, inputs.proposed.symbol: inputs.proposed.risk_R}
        projected = _heat_with_haircut(proj_syms, proj_risks, inputs.pairwise_correlations)

        cap = self._settings.max_portfolio_heat_R
        allowed = projected <= cap
        reasons: list[str] = []
        if not allowed:
            reasons.append(f"projected heat {projected:.2f}R exceeds cap {cap:.2f}R")
        return HeatDecision(
            allowed=allowed,
            current_heat_R=current,
            projected_heat_R=projected,
            reasons=reasons,
        )
