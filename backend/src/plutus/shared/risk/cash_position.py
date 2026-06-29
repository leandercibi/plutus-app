from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from plutus.config.settings import Settings


class _Signal(Protocol):
    expectancy_R: float


@dataclass(frozen=True)
class CashDecision:
    deploy_count: int
    cash_pct_of_pool: float
    reason: str


class CashAsPosition:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def decide(
        self, qualifying_signals: list[_Signal], pool_value: Decimal
    ) -> CashDecision:
        min_count = self._settings.cash_position_min_deploy_count
        k = len(qualifying_signals)

        if k >= min_count:
            return CashDecision(deploy_count=k, cash_pct_of_pool=0.0, reason="")

        deploy = sorted(qualifying_signals, key=lambda s: s.expectancy_R, reverse=True)
        deploy_count = len(deploy)
        cash_pct = (min_count - deploy_count) / min_count
        reason = (
            f"market offered {deploy_count} qualifying setups; "
            f"{cash_pct:.0%} of swing pool held in cash."
        )
        return CashDecision(
            deploy_count=deploy_count, cash_pct_of_pool=cash_pct, reason=reason
        )
