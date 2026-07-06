from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.risk.types import OpenPosition


class _Proposable(Protocol):
    symbol: str


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    max_correlation: float
    reasons: list[str] = field(default_factory=list)


class CorrelationGuard:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def check(
        self,
        open_positions: list[OpenPosition],
        proposed: _Proposable,
        returns_60d: pd.DataFrame,
    ) -> GuardDecision:
        if not open_positions or proposed.symbol not in returns_60d.columns:
            return GuardDecision(allowed=True, max_correlation=0.0)

        corr = returns_60d.corr()
        proposed_col = corr[proposed.symbol]
        max_corr = 0.0
        worst_symbol = ""
        for pos in open_positions:
            if pos.symbol in proposed_col.index:
                c = float(proposed_col[pos.symbol])
                if c > max_corr:
                    max_corr = c
                    worst_symbol = pos.symbol

        threshold = self._settings.pairwise_correlation_max
        allowed = max_corr <= threshold
        reasons: list[str] = []
        if not allowed:
            reasons.append(
                f"correlation {max_corr:.2f} with {worst_symbol} exceeds max {threshold:.2f}"
            )
        return GuardDecision(allowed=allowed, max_correlation=max_corr, reasons=reasons)
