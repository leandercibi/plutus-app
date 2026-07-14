from __future__ import annotations

import pandas as pd
import pytest

from plutus.shared.smart_money.delivery import DeliveryTrend, DeliveryTrendScore


def _delivery_frame(delivery_pcts: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"delivery_pct": delivery_pcts})


def _frame_with_today(today_pct: float) -> pd.DataFrame:
    # 20 prior sessions at a flat 0.40 median, then 5 rising sessions ending today.
    base = [0.40] * 20
    ramp = [0.42, 0.44, 0.46, 0.48, today_pct]
    return _delivery_frame(base + ramp)


def test_compute_returns_score_object() -> None:
    frame = _frame_with_today(0.50)
    out = DeliveryTrend().compute(frame, today_idx=len(frame) - 1)
    assert isinstance(out, DeliveryTrendScore)
    assert 0 <= out.score_0_15 <= 15


def test_today_above_median_with_positive_slope_scores_high() -> None:
    frame = _frame_with_today(0.55)  # well above 0.40 median, rising
    out = DeliveryTrend().compute(frame, today_idx=len(frame) - 1)
    assert out.score_0_15 >= 10
    assert out.trend_slope > 0
    assert out.delivery_pct_today == pytest.approx(0.55)


def test_today_at_median_scores_low() -> None:
    flat = _delivery_frame([0.40] * 25)
    out = DeliveryTrend().compute(flat, today_idx=len(flat) - 1)
    assert out.score_0_15 <= 5


def test_score_increases_monotonically_with_delivery_above_median() -> None:
    scores: list[int] = []
    for today in (0.41, 0.46, 0.52, 0.60, 0.70):
        frame = _frame_with_today(today)
        scores.append(DeliveryTrend().compute(frame, today_idx=len(frame) - 1).score_0_15)
    assert scores == sorted(scores)
    assert scores[-1] > scores[0]
