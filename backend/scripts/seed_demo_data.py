#!/usr/bin/env python3
"""Seed the local DB with realistic demo data so the dashboard shows useful content.

Run once after init_db:
    python scripts/seed_demo_data.py

Safe to re-run — deletes existing rows first.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

sys.path.insert(0, "src")

from plutus.db.init_db import init_db
from plutus.db.models import (
    AccumulationCandidate,
    AccumulationPosition,
    BundleStatPerRegime,
    CalibrationRow,
    Fill,
    RegimeSnapshot,
    SwingSignal,
    SwingTrade,
    Tranche,
    WeeklyPostmortem,
)
from plutus.db.session import session_scope

TODAY = date.today()
NOW = datetime.utcnow()
RUN_ID = "demo-run-001"


def clear(session):
    for model in [
        Fill,
        SwingTrade,
        SwingSignal,
        Tranche,
        AccumulationPosition,
        AccumulationCandidate,
        RegimeSnapshot,
        BundleStatPerRegime,
        CalibrationRow,
        WeeklyPostmortem,
    ]:
        session.query(model).delete()
    session.flush()


def seed(session):
    # --- Regime ---
    session.add(
        RegimeSnapshot(
            as_of_date=TODAY,
            label="BULL",
            nifty_close=Decimal("24350.50"),
            pct_above_50dma=0.68,
            pct_above_200dma=0.74,
            advance_decline=1.45,
            india_vix=13.2,
            fii_flow_inr=Decimal("2850000000"),
            dii_flow_inr=Decimal("1200000000"),
            breadth_confirmed_flip=False,
        )
    )

    # --- Swing signals ---
    _signals = [
        {
            "symbol": "RELIANCE",
            "bundle": "trend",
            "score": 81,
            "label": "BUY",
            "entry": Decimal("2940"),
            "stop_loss": Decimal("2840"),
            "target_1": Decimal("3100"),
            "target_2": Decimal("3280"),
            "expectancy_R": 0.52,
            "drawn_rr": 2.1,
            "regime_at_signal": "BULL",
            "counterfactual_text": "stays BUY unless entry slips above ₹2980 or regime flips",
            "pillar_breakdown_json": {
                "technical": 25,
                "expectancy": 20,
                "flow": 12,
                "sentiment": 4,
                "regime_fit": 13,
                "fundamentals": 7,
                "calibration_n": 68,
                "calibration_band": "high",
            },
        },
        {
            "symbol": "HDFCBANK",
            "bundle": "breakout",
            "score": 70,
            "label": "BUY_WATCH",
            "entry": Decimal("1710"),
            "stop_loss": Decimal("1650"),
            "target_1": Decimal("1820"),
            "target_2": Decimal("1940"),
            "expectancy_R": 0.38,
            "drawn_rr": 1.8,
            "regime_at_signal": "BULL",
            "counterfactual_text": "upgrades to BUY if delivery > 55% or entry < ₹1700",
            "pillar_breakdown_json": {
                "technical": 22,
                "expectancy": 16,
                "flow": 10,
                "sentiment": 3,
                "regime_fit": 12,
                "fundamentals": 7,
                "calibration_n": 42,
                "calibration_band": "medium",
            },
        },
        {
            "symbol": "INFY",
            "bundle": "vcp",
            "score": 77,
            "label": "BUY",
            "entry": Decimal("1895"),
            "stop_loss": Decimal("1820"),
            "target_1": Decimal("2020"),
            "target_2": Decimal("2140"),
            "expectancy_R": 0.45,
            "drawn_rr": 1.9,
            "regime_at_signal": "BULL",
            "counterfactual_text": "stays BUY unless sector IT underperforms 3 consecutive sessions",
            "pillar_breakdown_json": {
                "technical": 24,
                "expectancy": 18,
                "flow": 11,
                "sentiment": 4,
                "regime_fit": 13,
                "fundamentals": 7,
                "calibration_n": 55,
                "calibration_band": "high",
            },
        },
        {
            "symbol": "TITAN",
            "bundle": "composite",
            "score": 65,
            "label": "WATCH",
            "entry": Decimal("3480"),
            "stop_loss": Decimal("3350"),
            "target_1": Decimal("3680"),
            "target_2": Decimal("3850"),
            "expectancy_R": 0.28,
            "drawn_rr": 1.5,
            "regime_at_signal": "BULL",
            "counterfactual_text": "upgrades to BUY_WATCH if expectancy crosses 0.3R",
            "pillar_breakdown_json": {
                "technical": 19,
                "expectancy": 13,
                "flow": 9,
                "sentiment": 3,
                "regime_fit": 13,
                "fundamentals": 8,
                "calibration_n": 28,
                "calibration_band": "medium",
            },
        },
    ]
    sig_ids = []
    for s in _signals:
        sig = SwingSignal(run_id=RUN_ID, created_at=NOW, **s)
        session.add(sig)
        session.flush()
        sig_ids.append(sig.id)

    # --- Open trades ---
    trade1 = SwingTrade(
        signal_id=sig_ids[0],
        symbol="RELIANCE",
        bundle="trend",
        state="OPEN",
        opened_at=NOW - timedelta(days=4),
        qty=34,
        risk_R=1.0,
        realized_R=None,
        mfe_R=0.42,
        mae_R=-0.18,
    )
    session.add(trade1)
    session.flush()
    session.add(
        Fill(
            trade_id=trade1.id,
            kind="MOCK",
            side="BUY",
            qty=34,
            price=Decimal("2945"),
            cost_inr=Decimal("185.50"),
            slippage_bps=5.2,
            filled_at=NOW - timedelta(days=4),
        )
    )

    trade2 = SwingTrade(
        signal_id=sig_ids[2],
        symbol="INFY",
        bundle="vcp",
        state="T1_HIT",
        opened_at=NOW - timedelta(days=9),
        qty=52,
        risk_R=1.0,
        realized_R=None,
        mfe_R=1.12,
        mae_R=-0.08,
    )
    session.add(trade2)
    session.flush()
    session.add(
        Fill(
            trade_id=trade2.id,
            kind="MOCK",
            side="BUY",
            qty=52,
            price=Decimal("1898"),
            cost_inr=Decimal("156.80"),
            slippage_bps=4.8,
            filled_at=NOW - timedelta(days=9),
        )
    )

    # One recently closed trade
    closed_sig = SwingSignal(
        run_id=RUN_ID,
        symbol="TCS",
        bundle="trend",
        score=79,
        label="BUY",
        entry=Decimal("3920"),
        stop_loss=Decimal("3810"),
        target_1=Decimal("4100"),
        target_2=Decimal("4300"),
        expectancy_R=0.48,
        drawn_rr=2.0,
        regime_at_signal="BULL",
        pillar_breakdown_json={},
        created_at=NOW - timedelta(days=15),
    )
    session.add(closed_sig)
    session.flush()
    trade3 = SwingTrade(
        signal_id=closed_sig.id,
        symbol="TCS",
        bundle="trend",
        state="CLOSED_WIN",
        opened_at=NOW - timedelta(days=12),
        closed_at=NOW - timedelta(days=3),
        qty=25,
        risk_R=1.0,
        realized_R=1.82,
        mfe_R=1.95,
        mae_R=-0.12,
        exit_reason="T1_HIT",
    )
    session.add(trade3)

    # --- Accumulation candidates ---
    for sym, rs30, rs90, rs180, cagr in [
        ("BAJFINANCE", 72.1, 78.4, 82.0, 18.5),
        ("ASIANPAINT", 61.2, 69.8, 74.5, 14.2),
        ("LTIM", 55.0, 64.1, 68.9, 22.1),
    ]:
        session.add(
            AccumulationCandidate(
                run_id=RUN_ID,
                symbol=sym,
                score=72,
                rs_30=rs30,
                rs_90=rs90,
                rs_180=rs180,
                cagr_eps_3y=cagr,
                valuation_pillar_pct=0.22,
                thesis_text=f"{sym}: quality compounder, accumulate on dips",
                hard_avoid_active=False,
                created_at=NOW,
            )
        )

    # --- Accumulation position with tranches ---
    pos = AccumulationPosition(
        symbol="BAJFINANCE",
        state="BUILDING",
        avg_cost=Decimal("714"),
        qty_total=140,
        opened_at=NOW - timedelta(days=45),
        last_thesis_check_at=NOW - timedelta(days=7),
    )
    session.add(pos)
    session.flush()
    session.add(
        Tranche(
            position_id=pos.id,
            seq=1,
            atr_normalized_trigger_pct=0.015,
            filled_at_price=Decimal("742"),
            filled_at=NOW - timedelta(days=45),
            thesis_revalidated=True,
        )
    )
    session.add(
        Tranche(
            position_id=pos.id,
            seq=2,
            atr_normalized_trigger_pct=0.025,
            filled_at_price=Decimal("686"),
            filled_at=NOW - timedelta(days=21),
            thesis_revalidated=True,
        )
    )
    for seq in (3, 4, 5):
        session.add(
            Tranche(
                position_id=pos.id,
                seq=seq,
                atr_normalized_trigger_pct=0.015 * seq,
            )
        )

    # --- Bundle stats ---
    for bundle, regime, sharpe, exp_r, n in [
        ("trend", "BULL", 1.42, 0.52, 84),
        ("breakout", "BULL", 1.18, 0.41, 62),
        ("vcp", "BULL", 1.31, 0.48, 47),
        ("composite", "BULL", 1.55, 0.58, 38),
        ("trend", "BEAR", 0.38, 0.14, 22),
        ("breakout", "BEAR", 0.22, 0.08, 18),
    ]:
        session.add(
            BundleStatPerRegime(
                bundle=bundle,
                regime=regime,
                as_of_date=TODAY,
                oos_sharpe_shrunk=sharpe,
                oos_expectancy_R=exp_r,
                n_trades=n,
                ci_low=exp_r - 0.12,
                ci_high=exp_r + 0.15,
            )
        )

    # --- Calibration rows ---
    for bucket, regime, n, wr, exp_r in [
        ("trend_score_70_75", "BULL", 68, 0.62, 0.48),
        ("trend_score_75_80", "BULL", 84, 0.68, 0.55),
        ("breakout_score_70_75", "BULL", 42, 0.57, 0.38),
        ("vcp_score_75_80", "BULL", 55, 0.65, 0.46),
    ]:
        session.add(
            CalibrationRow(
                bucket=bucket,
                regime=regime,
                n_closed=n,
                win_rate=wr,
                expectancy_R=exp_r,
                ci_low_R=exp_r - 0.10,
                ci_high_R=exp_r + 0.12,
                sprt_state="accept_H1",
                last_updated=NOW,
                confidence_band="high" if n >= 50 else "medium",
            )
        )

    # --- Weekly postmortem ---
    week = TODAY - timedelta(days=TODAY.weekday() + 1)
    session.add(
        WeeklyPostmortem(
            week_ending=week,
            swing_return_pct=2.18,
            nifty_return_pct=0.84,
            regime_switched_return_pct=0.62,
            random_baseline_return_pct=-0.31,
            n_swing_trades_closed=6,
            drawdown_pct=1.2,
            report_md_path=f"reports/weekly/{week}.md",
        )
    )


if __name__ == "__main__":
    init_db()
    with session_scope() as s:
        clear(s)
        seed(s)
    print("✓ Demo data seeded. Run: streamlit run src/plutus/dashboard/app.py")
