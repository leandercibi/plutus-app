# tests/test_outcomes/test_tracker.py
"""
Outcome tracker tests using synthetic OHLCV bars.
No network calls — fetch_ohlcv is monkey-patched with a DataFrame builder.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from plutus.db.models import OutcomeVerdict, Recommendation, RecommendationVerdict, TradeOutcomesAudit
from plutus.db.session import Base
from plutus.weekly.outcomes import _evaluate, _score_bucket, track_recommendation_outcomes


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_rec(*, entry=100.0, stop=95.0, t1=110.0, t2=120.0, hold_max=10,
              confidence=75.0, strategy="trend", days_ago=5) -> Recommendation:
    created_at = datetime.utcnow() - timedelta(days=days_ago)
    return Recommendation(
        symbol="TEST",
        recommendation=RecommendationVerdict.BUY,
        confidence=confidence,
        entry_low=entry - 0.5,
        entry_high=entry + 0.5,
        entry_mid=entry,
        target1=t1,
        target2=t2,
        stop_loss=stop,
        hold_days_max=hold_max,
        strategy_used=strategy,
        created_at=created_at,
    )


def _df_from_bars(signal_date: date, bars: list[tuple[float, float, float]]) -> pd.DataFrame:
    """
    bars: list of (low, high, close) tuples, one per trading day after signal_date.
    Returns a DataFrame with DatetimeIndex.
    """
    rows = []
    d = signal_date + timedelta(days=1)
    for low, high, close in bars:
        rows.append({"Open": close, "High": high, "Low": low, "Close": close, "Volume": 1_000_000})
        d += timedelta(days=1)
    idx = pd.date_range(start=signal_date + timedelta(days=1), periods=len(bars), freq="D")
    return pd.DataFrame(rows, index=idx)


# ── _score_bucket ─────────────────────────────────────────────────────────────

def test_score_bucket_ranges():
    assert _score_bucket(85) == "70-100"
    assert _score_bucket(70) == "70-100"
    assert _score_bucket(69) == "55-69"
    assert _score_bucket(55) == "55-69"
    assert _score_bucket(50) == "35-54"
    assert _score_bucket(34) == "0-34"
    assert _score_bucket(None) == "UNKNOWN"


# ── _evaluate ─────────────────────────────────────────────────────────────────

def _patch_ohlcv(monkeypatch, bars):
    """Monkey-patch fetch_ohlcv to return synthetic bars."""
    import plutus.weekly.outcomes as mod
    rec_container = {}

    def fake_fetch(symbol, days=90, interval="1d", **kwargs):
        rec = rec_container["rec"]
        signal_date = rec.created_at.date()
        return _df_from_bars(signal_date, bars)

    monkeypatch.setattr(mod, "fetch_ohlcv", fake_fetch)
    return rec_container


def test_evaluate_hit_t1(monkeypatch):
    rec = _make_rec(entry=100, stop=95, t1=110, t2=120, hold_max=10)
    container = _patch_ohlcv(monkeypatch, [
        (98, 105, 103),  # day 1 — no hit
        (99, 111, 110),  # day 2 — high touches T1
    ])
    container["rec"] = rec
    result = _evaluate(rec, date.today())
    assert result is not None
    assert result["outcome"] == OutcomeVerdict.HIT_T1
    assert result["trading_days_held"] == 2
    assert result["outcome_pct"] == pytest.approx(10.0, abs=0.1)


def test_evaluate_hit_t2(monkeypatch):
    rec = _make_rec(entry=100, stop=95, t1=110, t2=120)
    container = _patch_ohlcv(monkeypatch, [
        (99, 121, 120),  # day 1 — high touches T2 (checked after SL and before T1 in code)
    ])
    container["rec"] = rec
    result = _evaluate(rec, date.today())
    assert result is not None
    assert result["outcome"] == OutcomeVerdict.HIT_T2


def test_evaluate_stopped(monkeypatch):
    rec = _make_rec(entry=100, stop=95, t1=110, t2=120, hold_max=10, days_ago=10)
    container = _patch_ohlcv(monkeypatch, [
        (98, 102, 100),   # day 1
        (98, 101, 100),   # day 2
        (98, 101, 100),   # day 3
        (93, 97, 95),     # day 4 — low dips below stop (past WRONG_DIRECTION_DAYS=3)
    ])
    container["rec"] = rec
    result = _evaluate(rec, date.today())
    assert result is not None
    assert result["outcome"] == OutcomeVerdict.STOPPED
    assert result["outcome_pct"] < 0


def test_evaluate_wrong_direction(monkeypatch):
    rec = _make_rec(entry=100, stop=95, t1=110, t2=120, days_ago=10)
    container = _patch_ohlcv(monkeypatch, [
        (93, 97, 95),  # day 1 — stop hit on first bar → WRONG_DIRECTION
    ])
    container["rec"] = rec
    result = _evaluate(rec, date.today())
    assert result is not None
    assert result["outcome"] == OutcomeVerdict.WRONG_DIRECTION
    assert result["trading_days_held"] == 1


def test_evaluate_expired(monkeypatch):
    rec = _make_rec(entry=100, stop=90, t1=115, t2=125, hold_max=3)
    # 3 bars, none hit target/stop → expired at bar 3
    container = _patch_ohlcv(monkeypatch, [
        (96, 103, 101),
        (97, 104, 102),
        (98, 105, 103),
    ])
    container["rec"] = rec
    result = _evaluate(rec, date.today())
    assert result is not None
    assert result["outcome"] == OutcomeVerdict.EXPIRED
    assert result["trading_days_held"] == 3


def test_evaluate_still_open(monkeypatch):
    rec = _make_rec(entry=100, stop=90, t1=115, t2=125, hold_max=10)
    container = _patch_ohlcv(monkeypatch, [
        (96, 103, 101),  # only 1 bar — hold_max not reached, no hit
    ])
    container["rec"] = rec
    result = _evaluate(rec, date.today())
    assert result is None


def test_evaluate_missing_fields_returns_none(monkeypatch):
    rec = _make_rec(entry=0, stop=0, t1=0)  # all zeros → invalid
    container = _patch_ohlcv(monkeypatch, [(98, 102, 100)])
    container["rec"] = rec
    result = _evaluate(rec, date.today())
    assert result is None


def test_evaluate_mfe_mae_captured(monkeypatch):
    rec = _make_rec(entry=100, stop=90, t1=115, t2=125, hold_max=5)
    container = _patch_ohlcv(monkeypatch, [
        (96, 108, 105),  # MFE bar: high=108 → 8%
        (93, 104, 100),  # MAE bar: low=93 → 7%
        (91, 103, 100),  # MAE bar: low=91 → 9%
        (95, 105, 102),
        (94, 106, 103),  # day 5 → EXPIRED
    ])
    container["rec"] = rec
    result = _evaluate(rec, date.today())
    assert result is not None
    assert result["mfe_pct"] == pytest.approx(8.0, abs=0.1)
    assert result["mae_pct"] == pytest.approx(9.0, abs=0.1)


def test_stop_first_on_ambiguous_bar(monkeypatch):
    """On a bar where both SL and T1 are touched, SL takes precedence."""
    rec = _make_rec(entry=100, stop=95, t1=110, t2=120, days_ago=10)
    container = _patch_ohlcv(monkeypatch, [
        (98, 102, 100),
        (98, 102, 100),
        (98, 102, 100),
        (93, 112, 105),  # day 4: low<stop AND high>T1 → STOPPED wins (stop-first)
    ])
    container["rec"] = rec
    result = _evaluate(rec, date.today())
    assert result["outcome"] == OutcomeVerdict.STOPPED


# ── track_recommendation_outcomes ─────────────────────────────────────────────

def test_track_updates_pending_rec(monkeypatch, db_session):
    import plutus.weekly.outcomes as mod

    rec = _make_rec(entry=100, stop=95, t1=110, t2=120, days_ago=5)
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)

    def fake_fetch(symbol, days=90, interval="1d", **kwargs):
        signal_date = rec.created_at.date()
        return _df_from_bars(signal_date, [(99, 111, 110)])  # T1 hit on day 1

    monkeypatch.setattr(mod, "fetch_ohlcv", fake_fetch)

    summary = track_recommendation_outcomes(db_session=db_session)

    assert summary["updated"] == 1
    assert summary["skipped"] == 0

    db_session.refresh(rec)
    assert rec.outcome == OutcomeVerdict.HIT_T1
    assert rec.mfe_pct is not None
    assert rec.mae_pct is not None

    audit_rows = db_session.query(TradeOutcomesAudit).all()
    assert len(audit_rows) == 1
    assert audit_rows[0].score_bucket == "70-100"


def test_track_skips_non_pending(monkeypatch, db_session):
    import plutus.weekly.outcomes as mod

    rec = _make_rec(days_ago=5)
    rec.outcome = OutcomeVerdict.HIT_T1  # already closed
    db_session.add(rec)
    db_session.commit()

    call_count = {"n": 0}

    def fake_fetch(*args, **kwargs):
        call_count["n"] += 1
        return pd.DataFrame()

    monkeypatch.setattr(mod, "fetch_ohlcv", fake_fetch)

    summary = track_recommendation_outcomes(db_session=db_session)
    assert summary["total"] == 0
    assert call_count["n"] == 0


def test_track_leaves_open_recs_pending(monkeypatch, db_session):
    import plutus.weekly.outcomes as mod

    rec = _make_rec(entry=100, stop=90, t1=115, hold_max=5, days_ago=5)
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)

    def fake_fetch(symbol, days=90, **kwargs):
        signal_date = rec.created_at.date()
        return _df_from_bars(signal_date, [(96, 103, 101)])  # 1 bar, no hit

    monkeypatch.setattr(mod, "fetch_ohlcv", fake_fetch)

    summary = track_recommendation_outcomes(db_session=db_session)
    assert summary["skipped"] == 1

    db_session.refresh(rec)
    assert rec.outcome == OutcomeVerdict.PENDING
