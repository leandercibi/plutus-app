from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TradeOutcome:
    trade_id: int
    bundle: str
    regime_at_signal: str
    score_bucket: str
    realized_R: float
    horizon_days: int
    closed_at: datetime
    is_paper: bool


def partition(
    outcomes: list[TradeOutcome],
) -> dict[tuple[str, str], list[TradeOutcome]]:
    """Returns {(score_bucket, regime): [outcome, ...]}."""
    out: dict[tuple[str, str], list[TradeOutcome]] = {}
    for o in outcomes:
        out.setdefault((o.score_bucket, o.regime_at_signal), []).append(o)
    return out
