from __future__ import annotations

from decimal import Decimal

from plutus.config.settings import Settings


class PositionSizer:
    """A6 — settings.risk_per_trade_pct is the ONLY source of per-trade risk."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def compute_qty(
        self,
        entry: Decimal,
        stop_loss: Decimal,
        pool_value: Decimal,
        adv_20d: int,
        governor_multiplier: float,
    ) -> int:
        risk_per_trade_inr = (
            pool_value
            * Decimal(str(self._settings.risk_per_trade_pct))
            * Decimal(str(governor_multiplier))
        )
        risk_per_share = entry - stop_loss
        if risk_per_share <= 0:
            raise ValueError("entry must exceed stop_loss for a long")
        qty_by_risk = risk_per_trade_inr / risk_per_share
        qty_by_adv = Decimal(adv_20d) * Decimal(str(self._settings.max_position_pct_of_adv))
        return int(min(qty_by_risk, qty_by_adv))
