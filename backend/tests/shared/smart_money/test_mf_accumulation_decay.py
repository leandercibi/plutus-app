from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from plutus.shared.smart_money.mf_accumulation import (
    MFAccumulation,
    MFAccumulationVerdict,
)


def _holdings(rows: list[tuple[date, float]]) -> pd.DataFrame:
    return pd.DataFrame({"as_of": [r[0] for r in rows], "mf_holding_pct": [r[1] for r in rows]})


def test_rising_holdings_is_accumulating() -> None:
    frame = _holdings(
        [
            (date(2025, 1, 1), 5.0),
            (date(2025, 2, 1), 6.0),
            (date(2025, 3, 1), 7.5),
        ]
    )
    out = MFAccumulation().evaluate(frame, as_of=date(2025, 3, 1))
    assert isinstance(out, MFAccumulationVerdict)
    assert out.verdict == "ACCUMULATING"


def test_falling_holdings_is_distributing() -> None:
    frame = _holdings(
        [
            (date(2025, 1, 1), 8.0),
            (date(2025, 2, 1), 6.5),
            (date(2025, 3, 1), 5.0),
        ]
    )
    out = MFAccumulation().evaluate(frame, as_of=date(2025, 3, 1))
    assert out.verdict == "DISTRIBUTING"


def test_flat_holdings_is_neutral() -> None:
    frame = _holdings(
        [
            (date(2025, 1, 1), 6.0),
            (date(2025, 2, 1), 6.0),
            (date(2025, 3, 1), 6.0),
        ]
    )
    out = MFAccumulation().evaluate(frame, as_of=date(2025, 3, 1))
    assert out.verdict == "NEUTRAL"


def test_decay_full_at_zero_days() -> None:
    frame = _holdings([(date(2025, 1, 1), 5.0), (date(2025, 3, 1), 7.0)])
    out = MFAccumulation().evaluate(frame, as_of=date(2025, 3, 1))
    assert out.age_days == 0
    assert out.confidence_after_decay == pytest.approx(1.0)


def test_decay_half_at_sixty_days() -> None:
    frame = _holdings([(date(2024, 11, 1), 5.0), (date(2025, 1, 1), 7.0)])
    out = MFAccumulation().evaluate(frame, as_of=date(2025, 3, 2))  # 60 days after Jan 1
    assert out.age_days == 60
    assert out.confidence_after_decay == pytest.approx(0.5)


def test_decay_zero_at_or_beyond_120_days() -> None:
    frame = _holdings([(date(2024, 6, 1), 5.0), (date(2024, 11, 1), 7.0)])
    out = MFAccumulation().evaluate(frame, as_of=date(2025, 3, 1))  # >120 days after Nov 1
    assert out.confidence_after_decay == pytest.approx(0.0)
