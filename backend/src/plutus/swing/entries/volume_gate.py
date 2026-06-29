from __future__ import annotations

import pandas as pd

from plutus.config.settings import Settings

_MEDIAN_WINDOW = 20


class VolumeGate:
    """A9 — delivery-adjusted volume confirmation gate.

    The confirmation candle's delivery-adjusted volume must exceed
    settings.volume_gate_delivery_mult times the 20-day median delivery-adjusted
    volume. On an expiry / index-rebalance day the gate is not applied (volume is
    not trustworthy), so it returns True unconditionally.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def passes(
        self,
        candles: pd.DataFrame,
        delivery: pd.DataFrame,
        today_idx: int,
        is_expiry_day: bool = False,
    ) -> bool:
        if is_expiry_day or self._is_expiry_from_column(delivery, today_idx):
            return True

        dav = delivery["traded_qty"] * delivery["delivery_pct"]
        window = dav.iloc[max(0, today_idx - _MEDIAN_WINDOW) : today_idx]
        if window.empty:
            return False
        median = float(window.median())
        if median <= 0:
            return False
        today_dav = float(dav.iloc[today_idx])
        return today_dav > self._settings.volume_gate_delivery_mult * median

    @staticmethod
    def _is_expiry_from_column(delivery: pd.DataFrame, today_idx: int) -> bool:
        if "is_expiry_or_rebalance_day" not in delivery.columns:
            return False
        return bool(delivery["is_expiry_or_rebalance_day"].iloc[today_idx])
