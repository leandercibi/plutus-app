from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from plutus.db.models import Base, Fill, SwingSignal, SwingTrade
from plutus.shared.fills.real_fill import log_real_fill, slippage_divergence_report


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _seed_trade(s: Session) -> int:
    sig = SwingSignal(
        run_id="r1",
        symbol="INFY",
        bundle="trend",
        score=80,
        label="BUY",
        entry=Decimal("100"),
        stop_loss=Decimal("95"),
        target_1=Decimal("110"),
        target_2=Decimal("120"),
        expectancy_R=0.5,
        drawn_rr=2.0,
        regime_at_signal="BULL",
        pillar_breakdown_json={},
        created_at=datetime(2025, 1, 1),
    )
    s.add(sig)
    s.flush()
    trade = SwingTrade(
        signal_id=sig.id,
        symbol="INFY",
        bundle="trend",
        state="OPEN",
        opened_at=datetime(2025, 1, 2),
        qty=100,
        risk_R=1.0,
    )
    s.add(trade)
    s.flush()
    return trade.id


def test_mock_and_real_fill_coexist_for_one_trade() -> None:
    s = _session()
    trade_id = _seed_trade(s)
    mock = Fill(
        trade_id=trade_id,
        kind="MOCK",
        side="BUY",
        qty=100,
        price=Decimal("101.00"),
        cost_inr=Decimal("130.00"),
        slippage_bps=5.0,
        filled_at=datetime(2025, 1, 2),
    )
    s.add(mock)
    s.commit()

    real = log_real_fill(
        trade_id=trade_id,
        side="BUY",
        qty=100,
        price=Decimal("101.50"),
        filled_at=datetime(2025, 1, 2),
        cost_inr=Decimal("131.00"),
        session=s,
    )
    s.commit()
    assert real.kind == "REAL"
    fills = s.query(Fill).filter_by(trade_id=trade_id).all()
    kinds = {f.kind for f in fills}
    assert kinds == {"MOCK", "REAL"}


def test_divergence_report_computes_stats() -> None:
    s = _session()
    trade_id = _seed_trade(s)
    s.add(
        Fill(
            trade_id=trade_id,
            kind="MOCK",
            side="BUY",
            qty=100,
            price=Decimal("100.00"),
            cost_inr=Decimal("130.00"),
            slippage_bps=5.0,
            filled_at=datetime(2025, 1, 2),
        )
    )
    log_real_fill(
        trade_id=trade_id,
        side="BUY",
        qty=100,
        price=Decimal("100.10"),  # 10 bps worse
        filled_at=datetime(2025, 1, 2),
        cost_inr=Decimal("131.00"),
        session=s,
    )
    s.commit()
    report = slippage_divergence_report(timedelta(days=30), session=s, now=datetime(2025, 1, 10))
    assert report.n_pairs == 1
    assert report.mean_bps > 0


def test_divergence_report_empty_window_no_crash() -> None:
    s = _session()
    report = slippage_divergence_report(timedelta(days=1), session=s, now=datetime(2025, 1, 10))
    assert report.n_pairs == 0
    assert report.mean_bps == 0.0
