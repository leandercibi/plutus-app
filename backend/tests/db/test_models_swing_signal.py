from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from plutus.db.models import SwingSignal


def _signal(
    label: str = "BUY",
    pillars: dict | None = None,
    counterfactual: str | None = "needs +1 ATR breakout",
) -> SwingSignal:
    return SwingSignal(
        run_id="run-001",
        symbol="INFY",
        bundle="trend",
        score=78,
        label=label,
        entry=Decimal("1500.00"),
        stop_loss=Decimal("1450.00"),
        target_1=Decimal("1600.00"),
        target_2=Decimal("1700.00"),
        expectancy_R=0.42,
        drawn_rr=1.8,
        regime_at_signal="BULL",
        pillar_breakdown_json=(pillars if pillars is not None else {"trend": 30, "flow": 12}),
        counterfactual_text=counterfactual,
        created_at=datetime(2025, 1, 1, 9, 15),
    )


def test_valid_labels_accepted(session: Session) -> None:
    for i, label in enumerate(("BUY", "BUY_WATCH", "WATCH", "HOLD", "AVOID")):
        sig = _signal(label=label)
        sig.symbol = f"SYM{i}"
        session.add(sig)
    session.commit()
    labels = {r.label for r in session.query(SwingSignal).all()}
    assert labels == {"BUY", "BUY_WATCH", "WATCH", "HOLD", "AVOID"}


def test_invalid_label_rejected(session: Session) -> None:
    session.add(_signal(label="STRONG_BUY"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_not_null_entry_rejected(session: Session) -> None:
    sig = _signal()
    sig.entry = None  # type: ignore[assignment]
    session.add(sig)
    with pytest.raises(IntegrityError):
        session.commit()


def test_round_trip_json_pillars(session: Session) -> None:
    pillars = {
        "technical": 28,
        "expectancy": 0.42,
        "flow": 13,
        "regime_fit": 15,
        "fundamentals": 8,
        "sentiment": 4,
    }
    session.add(_signal(pillars=pillars))
    session.commit()
    row = session.query(SwingSignal).filter_by(symbol="INFY").one()
    assert row.pillar_breakdown_json == pillars


def test_counterfactual_text_nullable(session: Session) -> None:
    session.add(_signal(counterfactual=None))
    session.commit()
    row = session.query(SwingSignal).filter_by(symbol="INFY").one()
    assert row.counterfactual_text is None
