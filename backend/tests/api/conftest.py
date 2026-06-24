from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from plutus.api.deps import get_app_settings, get_db
from plutus.api.main import create_app
from plutus.config.settings import Settings
from plutus.db.models import (
    AccumulationCandidate,
    AccumulationPosition,
    AlertCooldown,
    Base,
    CalibrationRow,
    Fill,
    RegimeSnapshot,
    SwingSignal,
    SwingTrade,
    Tranche,
    Universe,
    WeeklyPostmortem,
)

TEST_TOKEN = "test-operator-token"


@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_conn: object, _rec: object) -> None:
    cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


@pytest.fixture
def engine() -> Iterator[Engine]:
    # Shared in-memory DB: one connection reused across seed, request, and test
    # threads (TestClient runs the app in a worker thread).
    eng = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, future=True)


@pytest.fixture
def seed(session_factory: sessionmaker[Session]) -> None:
    s = session_factory()
    try:
        _seed_all(s)
        s.commit()
    finally:
        s.close()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, api_token=TEST_TOKEN)  # type: ignore[call-arg]


@pytest.fixture
def client(
    session_factory: sessionmaker[Session], settings: Settings, seed: None
) -> Iterator[TestClient]:
    app = create_app()

    def _override_db() -> Iterator[Session]:
        s = session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_app_settings] = lambda: settings
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


def _seed_all(s: Session) -> None:
    # --- regime ---
    s.add(
        RegimeSnapshot(
            as_of_date=date(2025, 1, 1),
            label="SIDEWAYS",
            nifty_close=Decimal("22000.00"),
            pct_above_50dma=0.5,
            pct_above_200dma=0.5,
            advance_decline=1.0,
            india_vix=15.0,
            fii_flow_inr=Decimal("100.00"),
            dii_flow_inr=Decimal("200.00"),
            breadth_confirmed_flip=False,
        )
    )
    s.add(
        RegimeSnapshot(
            as_of_date=date(2025, 1, 6),
            label="BULL",
            nifty_close=Decimal("22500.00"),
            pct_above_50dma=0.62,
            pct_above_200dma=0.58,
            advance_decline=1.8,
            india_vix=14.0,
            fii_flow_inr=Decimal("500.00"),
            dii_flow_inr=Decimal("300.00"),
            breadth_confirmed_flip=True,
        )
    )

    # --- universe PIT (two distinct dates) ---
    for sym in ("INFY", "TCS"):
        s.add(
            Universe(
                symbol=sym,
                as_of_date=date(2024, 1, 1),
                median_traded_value_inr=Decimal("100000000.00"),
                in_universe=True,
            )
        )
    for sym in ("INFY", "TCS", "RELIANCE"):
        s.add(
            Universe(
                symbol=sym,
                as_of_date=date(2025, 1, 6),
                median_traded_value_inr=Decimal("100000000.00"),
                in_universe=True,
            )
        )
    # one excluded member to prove the in_universe filter
    s.add(
        Universe(
            symbol="PENNY",
            as_of_date=date(2025, 1, 6),
            median_traded_value_inr=Decimal("1.00"),
            in_universe=False,
        )
    )

    # --- calibration ---
    s.add(
        CalibrationRow(
            bucket="trend_70_75",
            regime="BULL",
            n_closed=84,
            win_rate=0.6,
            expectancy_R=0.45,
            ci_low_R=0.2,
            ci_high_R=0.7,
            sprt_state="continue",
            last_updated=datetime(2025, 1, 6, 12, 0, 0),
            confidence_band="high",
        )
    )

    # --- swing signals ---
    s.add(
        SwingSignal(
            run_id="run-1",
            symbol="INFY",
            bundle="trend",
            score=76,
            label="BUY",
            entry=Decimal("1500.50"),
            stop_loss=Decimal("1450.00"),
            target_1=Decimal("1600.00"),
            target_2=Decimal("1700.00"),
            expectancy_R=0.45,
            drawn_rr=2.0,
            regime_at_signal="BULL",
            pillar_breakdown_json={
                "technical": 24,
                "expectancy": 0.45,
                "flow": 12,
                "regime_fit": 13,
                "fundamentals": 8,
                "sentiment": 3,
                "calibration_band": "high",
            },
            counterfactual_text="upgrades on delivery > 50%",
            created_at=datetime(2025, 1, 6, 9, 0, 0),
        )
    )
    s.add(
        SwingSignal(
            run_id="run-1",
            symbol="TCS",
            bundle="breakout",
            score=65,
            label="WATCH",
            entry=Decimal("4000.00"),
            stop_loss=Decimal("3900.00"),
            target_1=Decimal("4200.00"),
            target_2=Decimal("4400.00"),
            expectancy_R=0.1,
            drawn_rr=1.4,
            regime_at_signal="BULL",
            pillar_breakdown_json={
                "technical": 18,
                "expectancy": 0.1,
                "flow": 8,
                "regime_fit": 10,
                "fundamentals": 5,
                "sentiment": 2,
            },
            counterfactual_text=None,
            created_at=datetime(2025, 1, 6, 9, 1, 0),
        )
    )
    s.flush()

    # --- swing trades + fills ---
    open_trade = SwingTrade(
        signal_id=1,
        symbol="INFY",
        bundle="trend",
        state="OPEN",
        opened_at=datetime(2025, 1, 6, 9, 30, 0),
        qty=100,
        risk_R=1.0,
    )
    s.add(open_trade)
    # recently closed (within 7d of utcnow)
    s.add(
        SwingTrade(
            signal_id=2,
            symbol="TCS",
            bundle="breakout",
            state="CLOSED_WIN",
            opened_at=datetime.utcnow() - timedelta(days=3),
            closed_at=datetime.utcnow() - timedelta(days=1),
            qty=50,
            risk_R=1.0,
            realized_R=1.5,
            exit_reason="t1",
        )
    )
    # old closed (older than 7d) -> excluded from /positions
    s.add(
        SwingTrade(
            signal_id=2,
            symbol="OLDCO",
            bundle="trend",
            state="CLOSED_LOSS",
            opened_at=datetime.utcnow() - timedelta(days=40),
            closed_at=datetime.utcnow() - timedelta(days=39),
            qty=10,
            risk_R=1.0,
            realized_R=-1.0,
            exit_reason="sl",
        )
    )
    s.flush()

    # a mock fill on the open trade so a posted REAL fill can coexist (B10)
    s.add(
        Fill(
            trade_id=open_trade.id,
            kind="MOCK",
            side="BUY",
            qty=100,
            price=Decimal("1501.00"),
            cost_inr=Decimal("130.00"),
            slippage_bps=5.0,
            filled_at=datetime(2025, 1, 6, 9, 30, 0),
        )
    )

    # --- cooldowns (A16: separate rows per kind) ---
    s.add(
        AlertCooldown(
            symbol="INFY",
            kind="SL_WARNING",
            last_fired_at=datetime(2025, 1, 6, 10, 0, 0),
        )
    )
    s.add(
        AlertCooldown(
            symbol="INFY",
            kind="SL_BREACH",
            last_fired_at=datetime(2025, 1, 6, 11, 0, 0),
        )
    )

    # --- accumulation ---
    s.add(
        AccumulationCandidate(
            run_id="run-1",
            symbol="HDFCBANK",
            score=78,
            rs_30=0.68,
            rs_90=0.72,
            rs_180=0.74,
            cagr_eps_3y=0.15,
            valuation_pillar_pct=28.0,
            thesis_text="quality compounder",
            hard_avoid_active=False,
            created_at=datetime(2025, 1, 6, 8, 0, 0),
        )
    )
    s.add(
        AccumulationCandidate(
            run_id="run-1",
            symbol="VALUETRAP",
            score=40,
            rs_30=-0.1,
            rs_90=-0.2,
            rs_180=-0.3,
            cagr_eps_3y=-0.05,
            valuation_pillar_pct=30.0,
            thesis_text="cheap but declining",
            hard_avoid_active=True,
            created_at=datetime(2025, 1, 6, 8, 1, 0),
        )
    )
    pos = AccumulationPosition(
        symbol="HDFCBANK",
        state="BUILDING",
        avg_cost=Decimal("1650.00"),
        qty_total=200,
        opened_at=datetime(2025, 1, 1, 9, 0, 0),
        last_thesis_check_at=datetime(2025, 1, 6, 9, 0, 0),
    )
    s.add(pos)
    s.flush()
    # tranches out of seq order to prove ordering by seq
    s.add(
        Tranche(
            position_id=pos.id,
            seq=2,
            atr_normalized_trigger_pct=0.05,
            filled_at_price=Decimal("1640.00"),
            filled_at=datetime(2025, 1, 3, 9, 0, 0),
            thesis_revalidated=True,
        )
    )
    s.add(
        Tranche(
            position_id=pos.id,
            seq=1,
            atr_normalized_trigger_pct=0.0,
            filled_at_price=Decimal("1650.00"),
            filled_at=datetime(2025, 1, 1, 9, 0, 0),
            thesis_revalidated=True,
        )
    )
    s.add(
        Tranche(
            position_id=pos.id,
            seq=3,
            atr_normalized_trigger_pct=0.08,
            filled_at_price=None,
            filled_at=None,
            thesis_revalidated=False,
        )
    )

    # --- postmortem / benchmarks ---
    s.add(
        WeeklyPostmortem(
            week_ending=date(2025, 1, 5),
            swing_return_pct=3.2,
            nifty_return_pct=1.1,
            regime_switched_return_pct=0.8,
            random_baseline_return_pct=-0.4,
            n_swing_trades_closed=12,
            drawdown_pct=2.0,
            report_md_path="reports/weekly/2025-01-05.md",
        )
    )
