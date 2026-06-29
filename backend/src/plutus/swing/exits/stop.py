from __future__ import annotations

from plutus.shared.fills.policy import FillPolicy, FillResult
from plutus.shared.fills.types import OHLCBar, TradePlan


class StopExit:
    """Simple SL hit detection; delegates fill mechanics to shared/fills/policy.py."""

    def check(
        self,
        plan: TradePlan,
        bar: OHLCBar,
        fills: FillPolicy,
        adv: int,
        atr_pct: float,
        qty: int = 1,
    ) -> FillResult | None:
        return fills.fill_stop(plan, bar, adv, atr_pct, qty)
