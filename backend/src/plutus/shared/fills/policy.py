from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Literal

from plutus.shared.cost_model.slippage import SlippageModel
from plutus.shared.fills.types import OHLCBar, TradePlan

_MARKET_CLOSE = time(15, 30)


@dataclass(frozen=True)
class FillResult:
    side: Literal["BUY", "SELL"]
    qty: int
    price: Decimal
    slippage_bps: float
    filled_at: datetime


def _filled_at(bar: OHLCBar) -> datetime:
    return datetime.combine(bar.as_of, _MARKET_CLOSE)


class FillPolicy:
    """A1 — no same-bar look-ahead; gap-through stops fill at the worse price."""

    def __init__(self, slippage: SlippageModel) -> None:
        self._slippage = slippage

    def fill_entry(
        self, plan: TradePlan, next_bar: OHLCBar, adv: int, atr_pct: float, qty: int = 1
    ) -> FillResult:
        bps = self._slippage.slippage_bps(qty, adv, atr_pct)
        price = self._slippage.apply_to_price(next_bar.open, "BUY", bps)
        return FillResult("BUY", qty, price, bps, _filled_at(next_bar))

    def fill_stop(
        self, plan: TradePlan, next_bar: OHLCBar, adv: int, atr_pct: float, qty: int = 1
    ) -> FillResult | None:
        triggered = next_bar.low <= plan.stop_loss or next_bar.open <= plan.stop_loss
        if not triggered:
            return None
        worse = min(plan.stop_loss, next_bar.open)  # SELL: lower is worse
        bps = self._slippage.slippage_bps(qty, adv, atr_pct)
        price = self._slippage.apply_to_price(worse, "SELL", bps)
        return FillResult("SELL", qty, price, bps, _filled_at(next_bar))

    def fill_target(
        self,
        plan: TradePlan,
        next_bar: OHLCBar,
        target_level: Literal[1, 2],
        adv: int,
        atr_pct: float,
        qty: int = 1,
    ) -> FillResult | None:
        target = plan.target_1 if target_level == 1 else plan.target_2
        if next_bar.high < target:
            return None
        gap_through = next_bar.open >= target
        base = next_bar.open if gap_through else target
        bps = self._slippage.slippage_bps(qty, adv, atr_pct)
        price = self._slippage.apply_to_price(base, "SELL", bps)
        return FillResult("SELL", qty, price, bps, _filled_at(next_bar))
