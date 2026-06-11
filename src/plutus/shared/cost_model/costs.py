from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from plutus.config.settings import Settings

_QUANT = Decimal("0.0001")
_BROKERAGE_PCT = Decimal("0.0003")


@dataclass(frozen=True)
class CostBreakdown:
    brokerage: Decimal
    stt: Decimal
    exchange: Decimal
    gst: Decimal
    stamp_duty: Decimal
    total: Decimal


def _q(x: Decimal) -> Decimal:
    return x.quantize(_QUANT, rounding=ROUND_HALF_UP)


class CostModel:
    def __init__(self, settings: Settings) -> None:
        self._brokerage_cap = Decimal(str(settings.brokerage_per_order_inr))
        self._stt_pct = Decimal(str(settings.stt_pct))
        self._exchange_pct = Decimal(str(settings.exchange_pct))
        self._gst_pct = Decimal(str(settings.gst_pct))
        self._stamp_duty_pct = Decimal(str(settings.stamp_duty_pct))

    def _leg(self, qty: int, price: Decimal, *, stamp: bool) -> CostBreakdown:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if price <= 0:
            raise ValueError("price must be positive")
        notional = Decimal(qty) * price
        brokerage = min(self._brokerage_cap, notional * _BROKERAGE_PCT)
        stt = notional * self._stt_pct
        exchange = notional * self._exchange_pct
        gst = (brokerage + exchange) * self._gst_pct
        stamp_duty = notional * self._stamp_duty_pct if stamp else Decimal("0")
        total = brokerage + stt + exchange + gst + stamp_duty
        return CostBreakdown(
            brokerage=_q(brokerage),
            stt=_q(stt),
            exchange=_q(exchange),
            gst=_q(gst),
            stamp_duty=_q(stamp_duty),
            total=_q(total),
        )

    def buy_cost(self, qty: int, price: Decimal) -> CostBreakdown:
        return self._leg(qty, price, stamp=True)

    def sell_cost(self, qty: int, price: Decimal) -> CostBreakdown:
        return self._leg(qty, price, stamp=False)

    def round_trip_cost(self, qty: int, entry: Decimal, exit: Decimal) -> Decimal:
        return self.buy_cost(qty, entry).total + self.sell_cost(qty, exit).total
