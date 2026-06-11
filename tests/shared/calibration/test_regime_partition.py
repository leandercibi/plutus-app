from __future__ import annotations

from datetime import datetime

from plutus.shared.calibration.regime_partition import TradeOutcome, partition


def _o(bucket: str, regime: str, r: float) -> TradeOutcome:
    return TradeOutcome(
        trade_id=1,
        bundle="trend",
        regime_at_signal=regime,
        score_bucket=bucket,
        realized_R=r,
        horizon_days=5,
        closed_at=datetime(2025, 1, 1),
        is_paper=False,
    )


def test_partition_buckets_by_bucket_and_regime() -> None:
    outcomes = [
        _o("score_70_75", "BULL", 1.0),
        _o("score_70_75", "BULL", -1.0),
        _o("score_70_75", "BEAR", 0.5),
        _o("score_75_80", "BULL", 2.0),
    ]
    parts = partition(outcomes)
    assert len(parts[("score_70_75", "BULL")]) == 2
    assert len(parts[("score_70_75", "BEAR")]) == 1
    assert len(parts[("score_75_80", "BULL")]) == 1
