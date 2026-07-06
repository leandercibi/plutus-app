from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

_DECAY_FULL_DAYS = 0
_DECAY_HALF_DAYS = 60
_DECAY_ZERO_DAYS = 120
_NEUTRAL_BAND = 0.25  # holding-pct change within +/-0.25pp is neutral

Verdict = Literal["ACCUMULATING", "DISTRIBUTING", "NEUTRAL"]


@dataclass(frozen=True)
class MFAccumulationVerdict:
    verdict: Verdict
    age_days: int
    confidence_after_decay: float


class MFAccumulation:
    """A7 age-decay. Mutual-fund holding trend with linear confidence decay:
    1.0 at 0 days since the latest observation, 0.5 at 60 days, 0.0 at 120+."""

    def evaluate(self, mf_holdings_history: pd.DataFrame, as_of: date) -> MFAccumulationVerdict:
        ordered = mf_holdings_history.sort_values("as_of").reset_index(drop=True)
        first = float(ordered["mf_holding_pct"].iloc[0])
        last = float(ordered["mf_holding_pct"].iloc[-1])
        latest_obs = ordered["as_of"].iloc[-1]
        if hasattr(latest_obs, "date"):
            latest_obs = latest_obs.date()

        change = last - first
        if change > _NEUTRAL_BAND:
            verdict: Verdict = "ACCUMULATING"
        elif change < -_NEUTRAL_BAND:
            verdict = "DISTRIBUTING"
        else:
            verdict = "NEUTRAL"

        age_days = (as_of - latest_obs).days
        confidence = self._decay(age_days)
        return MFAccumulationVerdict(
            verdict=verdict, age_days=age_days, confidence_after_decay=confidence
        )

    @staticmethod
    def _decay(age_days: int) -> float:
        if age_days <= _DECAY_FULL_DAYS:
            return 1.0
        if age_days >= _DECAY_ZERO_DAYS:
            return 0.0
        return 1.0 - age_days / _DECAY_ZERO_DAYS
