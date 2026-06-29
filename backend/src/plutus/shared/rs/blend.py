"""Shared relative-strength blend — usable by both swing and accumulation.

Moved from ``plutus.accumulation.rs.blend`` so that ``plutus.swing`` can import
it without violating the swing-accumulation independence contract.
``plutus.accumulation.rs.blend`` re-exports from here for backwards compat.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# A12 — RS blend weights: heavier on the longer horizons.
_W_30 = 0.2
_W_90 = 0.4
_W_180 = 0.4

_LOOKBACK_30 = 30
_LOOKBACK_90 = 90
_LOOKBACK_180 = 180


@dataclass(frozen=True)
class RSBlendResult:
    rs_30: float
    rs_90: float
    rs_180: float
    blended: float


class RSBlend:
    """A12 — 30/90/180-day relative-strength blend vs Nifty."""

    def compute(self, candles: pd.DataFrame, nifty_candles: pd.DataFrame) -> RSBlendResult:
        rs_30 = self._relative_return(candles, nifty_candles, _LOOKBACK_30)
        rs_90 = self._relative_return(candles, nifty_candles, _LOOKBACK_90)
        rs_180 = self._relative_return(candles, nifty_candles, _LOOKBACK_180)
        blended = _W_30 * rs_30 + _W_90 * rs_90 + _W_180 * rs_180
        return RSBlendResult(rs_30=rs_30, rs_90=rs_90, rs_180=rs_180, blended=blended)

    def _relative_return(
        self, candles: pd.DataFrame, nifty_candles: pd.DataFrame, lookback: int
    ) -> float:
        return self._period_return(candles, lookback) - self._period_return(
            nifty_candles, lookback
        )

    def _period_return(self, candles: pd.DataFrame, lookback: int) -> float:
        close = candles["close"].to_numpy(dtype=float)
        if len(close) <= lookback:
            raise ValueError(
                f"need more than {lookback} candles for the RS lookback, got {len(close)}"
            )
        start = close[-(lookback + 1)]
        end = close[-1]
        if start <= 0.0:
            raise ValueError("non-positive start price in RS lookback window")
        return float(end / start - 1.0)
