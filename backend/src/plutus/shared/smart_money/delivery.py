from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

_MEDIAN_WINDOW = 20
_SLOPE_WINDOW = 5
_ABOVE_MEDIAN_THRESHOLD = 0.05  # 5 percentage points
_MAX_SCORE = 15


@dataclass(frozen=True)
class DeliveryTrendScore:
    score_0_15: int
    delivery_pct_today: float
    delivery_pct_20d_median: float
    trend_slope: float


class DeliveryTrend:
    """A9 input. Higher conviction when today's delivery percentage clears the
    20-day median by more than 5pp and the recent 5-session slope is positive."""

    def compute(self, delivery: pd.DataFrame, today_idx: int) -> DeliveryTrendScore:
        series = delivery["delivery_pct"].to_numpy(dtype=float)
        today = float(series[today_idx])

        window_start = max(0, today_idx - _MEDIAN_WINDOW)
        prior = series[window_start:today_idx]
        median = float(np.median(prior)) if prior.size else today

        slope_start = max(0, today_idx - _SLOPE_WINDOW + 1)
        slope_vals = series[slope_start : today_idx + 1]
        trend_slope = self._slope(slope_vals)

        excess = today - median
        # gradient component scales with how far above median (capped), in [0, 12]
        gradient = max(0.0, excess) / _ABOVE_MEDIAN_THRESHOLD
        excess_points = min(12.0, gradient * 6.0)
        slope_points = 3.0 if trend_slope > 0 else 0.0
        score = int(round(min(float(_MAX_SCORE), excess_points + slope_points)))

        return DeliveryTrendScore(
            score_0_15=score,
            delivery_pct_today=today,
            delivery_pct_20d_median=median,
            trend_slope=trend_slope,
        )

    @staticmethod
    def _slope(values: np.ndarray) -> float:
        if values.size < 2:
            return 0.0
        x = np.arange(values.size, dtype=float)
        slope, _ = np.polyfit(x, values, 1)
        return float(slope)
