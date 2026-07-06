from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from plutus.config.settings import Settings

_DEFAULT_CIRCUIT_PCT = 0.20


@dataclass(frozen=True)
class CircuitStatus:
    hit_count: int
    last_hit_date: date | None
    suppress: bool


class CircuitGate:
    """B7 — flags symbols that recently hit a price circuit (limit) band.

    A bar is a circuit hit when it is locked (high == low) or its absolute move
    from the prior close is at least the circuit percentage. Recent hits within
    the lookback window recommend suppression of the setup (the breakout bundle
    overrides this only for >2 ATR moves).
    """

    def __init__(self, settings: Settings, circuit_pct: float = _DEFAULT_CIRCUIT_PCT) -> None:
        self._settings = settings
        self._circuit_pct = circuit_pct

    def status(
        self, symbol: str, candles: pd.DataFrame, lookback_sessions: int = 90
    ) -> CircuitStatus:
        window = candles.iloc[-lookback_sessions:].reset_index(drop=True)
        highs = [float(x) for x in window["high"].tolist()]
        lows = [float(x) for x in window["low"].tolist()]
        closes = [float(x) for x in window["close"].tolist()]
        dates = [pd.Timestamp(x).date() for x in window["date"].tolist()]

        hit_dates: list[date] = []
        for i in range(1, len(window)):
            locked = highs[i] == lows[i]
            prior_close = closes[i - 1]
            move = abs(closes[i] - prior_close) / prior_close if prior_close > 0 else 0.0
            if locked or move >= self._circuit_pct:
                hit_dates.append(dates[i])

        hit_count = len(hit_dates)
        return CircuitStatus(
            hit_count=hit_count,
            last_hit_date=hit_dates[-1] if hit_dates else None,
            suppress=hit_count > 0,
        )
