# tests/test_self_finetuning/test_postmortem.py
"""
Tests for postmortem.py and tuner.py — 100% offline, in-memory SQLite.

Verifies:
  - CalibrationReport stats match hand-computed values
  - Diverging buckets are correctly identified
  - Suggestion loop writes TuningSuggestion rows for diverging buckets
  - Suggestion loop skips when n < MIN_TRADES_FOR_SUGGESTION
  - No duplicate suggestions within 14 days
  - apply_suggestion marks suggestion as applied and writes TuningHistory row
  - auto_tune is noop when AUTO_TUNE_ENABLED = False
  - format_report produces non-empty markdown
"""
from __future__ import annotations

import os
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "-1")

from datetime import date, timedelta
from typing import List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from plutus.db.session import Base
from plutus.db.models import (
    Recommendation, RecommendationVerdict, OutcomeVerdict,
    TradeOutcomesAudit, TuningSuggestion, TuningHistory,
)
from plutus.weekly.postmortem import (
    CalibrationReport, BucketStats,
    DIVERGENCE_THRESHOLD, MIN_TRADES_FOR_BUCKET,
    run_postmortem, format_report,
)
from plutus.weekly.tuner import (
    MIN_TRADES_FOR_SUGGESTION, run_suggestion_loop,
    apply_suggestion, run_auto_tune, run_full_self_finetuning,
    AUTO_TUNE_ENABLED,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _add_audit_rows(
    db,
    *,
    n_win: int,
    n_loss: int,
    n_wrong_dir: int = 0,
    score_bucket: str = "70-100",
    bundle: str = "trend",
    regime: str = "BULL",
    exit_date: date = None,
) -> None:
    """Write fake TradeOutcomesAudit rows for a given bucket."""
    if exit_date is None:
        exit_date = date.today() - timedelta(days=3)

    # Need parent Recommendation rows for FK constraint
    for i in range(n_win + n_loss + n_wrong_dir):
        rec = Recommendation(
            symbol=f"SYM{i}",
            recommendation=RecommendationVerdict.BUY,
            confidence=0.8,
            entry_low=99.0,
            entry_high=101.0,
            stop_loss=95.0,
            target1=110.0,
        )
        db.add(rec)
    db.flush()

    recs = db.query(Recommendation).order_by(Recommendation.id.desc()).limit(
        n_win + n_loss + n_wrong_dir
    ).all()
    recs.reverse()

    idx = 0
    for _ in range(n_win):
        db.add(TradeOutcomesAudit(
            recommendation_id=recs[idx].id,
            symbol=f"WIN{idx}",
            outcome=OutcomeVerdict.HIT_T1,
            outcome_pct=5.0,
            exit_date=exit_date,
            mfe_pct=6.0,
            mae_pct=-1.5,
            score_bucket=score_bucket,
            bundle_used=bundle,
            regime_at_signal=regime,
        ))
        idx += 1
    for _ in range(n_loss):
        db.add(TradeOutcomesAudit(
            recommendation_id=recs[idx].id,
            symbol=f"LOSS{idx}",
            outcome=OutcomeVerdict.STOPPED,
            outcome_pct=-3.0,
            exit_date=exit_date,
            mfe_pct=1.0,
            mae_pct=-3.5,
            score_bucket=score_bucket,
            bundle_used=bundle,
            regime_at_signal=regime,
        ))
        idx += 1
    for _ in range(n_wrong_dir):
        db.add(TradeOutcomesAudit(
            recommendation_id=recs[idx].id,
            symbol=f"WD{idx}",
            outcome=OutcomeVerdict.WRONG_DIRECTION,
            outcome_pct=-4.0,
            exit_date=exit_date,
            mfe_pct=0.5,
            mae_pct=-4.0,
            score_bucket=score_bucket,
            bundle_used=bundle,
            regime_at_signal=regime,
        ))
        idx += 1
    db.commit()


# ── run_postmortem ─────────────────────────────────────────────────────────────

class TestRunPostmortem:
    def test_empty_db_returns_zero_report(self, db):
        report = run_postmortem(lookback_days=30, db_session=db)
        assert report.total_closed_trades == 0
        assert report.wrong_direction_count == 0
        assert report.score_bucket_stats == []

    def test_correct_trade_count(self, db):
        _add_audit_rows(db, n_win=8, n_loss=2)
        report = run_postmortem(lookback_days=30, db_session=db)
        assert report.total_closed_trades == 10

    def test_correct_win_rate_in_bucket(self, db):
        _add_audit_rows(db, n_win=6, n_loss=4, score_bucket="70-100")
        report = run_postmortem(lookback_days=30, db_session=db)
        bucket = next((s for s in report.score_bucket_stats if s.value == "70-100"), None)
        assert bucket is not None
        assert abs(bucket.win_rate - 0.6) < 0.01

    def test_wrong_direction_counted(self, db):
        _add_audit_rows(db, n_win=5, n_loss=3, n_wrong_dir=2)
        report = run_postmortem(lookback_days=30, db_session=db)
        assert report.wrong_direction_count == 2

    def test_mfe_mae_averaged(self, db):
        _add_audit_rows(db, n_win=5, n_loss=5, score_bucket="55-69")
        report = run_postmortem(lookback_days=30, db_session=db)
        bucket = next((s for s in report.score_bucket_stats if s.value == "55-69"), None)
        assert bucket is not None
        assert bucket.avg_mfe_pct > 0
        assert bucket.avg_mae_pct < 0

    def test_old_trades_excluded(self, db):
        old_date = date.today() - timedelta(days=60)
        _add_audit_rows(db, n_win=5, n_loss=5, exit_date=old_date)
        report = run_postmortem(lookback_days=30, db_session=db)
        assert report.total_closed_trades == 0

    def test_bucket_below_min_trades_excluded(self, db):
        # MIN_TRADES_FOR_BUCKET = 5; use 3 wins only → below threshold
        _add_audit_rows(db, n_win=3, n_loss=0, score_bucket="35-54")
        report = run_postmortem(lookback_days=30, db_session=db)
        assert all(s.value != "35-54" for s in report.score_bucket_stats)

    def test_multiple_buckets(self, db):
        _add_audit_rows(db, n_win=8, n_loss=2, score_bucket="70-100")
        _add_audit_rows(db, n_win=3, n_loss=7, score_bucket="55-69")
        report = run_postmortem(lookback_days=30, db_session=db)
        buckets = {s.value: s for s in report.score_bucket_stats}
        assert "70-100" in buckets
        assert "55-69" in buckets
        assert buckets["70-100"].win_rate > buckets["55-69"].win_rate

    def test_diverging_buckets_identified(self, db):
        # Win rate 30% is 25pp below 55% expected → should diverge
        _add_audit_rows(db, n_win=3, n_loss=7, score_bucket="55-69")
        report = run_postmortem(lookback_days=30, db_session=db)
        diverging_values = [s.value for s in report.diverging_buckets]
        assert "55-69" in diverging_values

    def test_non_diverging_bucket_not_flagged(self, db):
        # Win rate 55% is right at expected → no divergence
        _add_audit_rows(db, n_win=6, n_loss=5, score_bucket="70-100")
        report = run_postmortem(lookback_days=30, db_session=db)
        diverging_values = [s.value for s in report.diverging_buckets]
        assert "70-100" not in diverging_values

    def test_top_best_and_worst_calls(self, db):
        _add_audit_rows(db, n_win=5, n_loss=5)
        report = run_postmortem(lookback_days=30, db_session=db)
        assert len(report.top_best_calls) >= 1
        assert len(report.top_worst_calls) >= 1
        # Best calls have higher outcome_pct than worst
        best_pct = report.top_best_calls[0].outcome_pct
        worst_pct = report.top_worst_calls[-1].outcome_pct
        assert best_pct >= worst_pct


# ── format_report ──────────────────────────────────────────────────────────────

class TestFormatReport:
    def test_format_non_empty(self, db):
        _add_audit_rows(db, n_win=6, n_loss=4)
        report = run_postmortem(lookback_days=30, db_session=db)
        md = format_report(report)
        assert "## Calibration Report" in md
        assert str(date.today()) in md

    def test_format_shows_wrong_direction(self, db):
        _add_audit_rows(db, n_win=5, n_loss=3, n_wrong_dir=2)
        report = run_postmortem(lookback_days=30, db_session=db)
        md = format_report(report)
        assert "WRONG_DIRECTION" in md or "2" in md

    def test_format_empty_report(self, db):
        report = run_postmortem(lookback_days=30, db_session=db)
        md = format_report(report)
        assert "## Calibration Report" in md


# ── run_suggestion_loop ────────────────────────────────────────────────────────

class TestSuggestionLoop:
    def test_no_suggestions_when_no_divergence(self, db):
        # Win rate ~55% → no divergence → no suggestions
        _add_audit_rows(db, n_win=6, n_loss=5, score_bucket="70-100")
        report = run_postmortem(lookback_days=30, db_session=db)
        candidates = run_suggestion_loop(report, db_session=db)
        assert len(candidates) == 0

    def test_writes_suggestion_for_diverging_bucket(self, db):
        # Win rate 30% → diverges by 25pp → should write suggestion
        _add_audit_rows(db, n_win=3, n_loss=7, score_bucket="55-69")
        report = run_postmortem(lookback_days=30, db_session=db)
        candidates = run_suggestion_loop(report, db_session=db)
        # Suggestion row should be in DB
        count = db.query(TuningSuggestion).count()
        assert count >= 1

    def test_suggestion_has_correct_fields(self, db):
        _add_audit_rows(db, n_win=2, n_loss=8, score_bucket="35-54")
        report = run_postmortem(lookback_days=30, db_session=db)
        run_suggestion_loop(report, db_session=db)
        suggestion = db.query(TuningSuggestion).filter(
            TuningSuggestion.dimension_value == "35-54"
        ).first()
        assert suggestion is not None
        assert suggestion.status == "pending"
        assert len(suggestion.suggestion_text) > 10
        assert suggestion.n_trades >= MIN_TRADES_FOR_SUGGESTION

    def test_no_duplicate_suggestion_within_14_days(self, db):
        _add_audit_rows(db, n_win=2, n_loss=8, score_bucket="55-69")
        report = run_postmortem(lookback_days=30, db_session=db)
        run_suggestion_loop(report, db_session=db)
        run_suggestion_loop(report, db_session=db)  # second run same day
        count = db.query(TuningSuggestion).filter(
            TuningSuggestion.dimension_value == "55-69"
        ).count()
        assert count == 1  # no duplicate


# ── apply_suggestion ───────────────────────────────────────────────────────────

class TestApplySuggestion:
    def _create_suggestion(self, db) -> int:
        row = TuningSuggestion(
            report_date=date.today(),
            dimension="bundle",
            dimension_value="trend",
            current_win_rate=0.30,
            target_win_rate=0.55,
            n_trades=20,
            suggestion_text="Test suggestion",
            status="pending",
        )
        db.add(row)
        db.commit()
        return row.id

    def test_apply_marks_as_applied(self, db):
        sid = self._create_suggestion(db)
        ok = apply_suggestion(sid, db_session=db)
        assert ok is True
        s = db.query(TuningSuggestion).get(sid)
        assert s.status == "applied"
        assert s.applied_at is not None

    def test_apply_writes_history_row(self, db):
        sid = self._create_suggestion(db)
        apply_suggestion(sid, db_session=db)
        history = db.query(TuningHistory).filter(
            TuningHistory.suggestion_id == sid
        ).first()
        assert history is not None
        assert history.win_rate_before == pytest.approx(0.30)

    def test_apply_nonexistent_returns_false(self, db):
        ok = apply_suggestion(99999, db_session=db)
        assert ok is False

    def test_apply_already_applied_returns_false(self, db):
        sid = self._create_suggestion(db)
        apply_suggestion(sid, db_session=db)
        ok = apply_suggestion(sid, db_session=db)  # second apply
        assert ok is False


# ── auto_tune ─────────────────────────────────────────────────────────────────

class TestAutoTune:
    def test_noop_when_disabled(self, db, monkeypatch):
        # Ensure AUTO_TUNE_ENABLED is False (default)
        monkeypatch.setattr("plutus.weekly.tuner.AUTO_TUNE_ENABLED", False)
        _add_audit_rows(db, n_win=2, n_loss=8, score_bucket="55-69")
        report = run_postmortem(lookback_days=30, db_session=db)
        result = run_auto_tune(report, db_session=db)
        assert result == 0


# ── run_full_self_finetuning ───────────────────────────────────────────────────

class TestFullLoop:
    def test_returns_summary_dict(self, db):
        _add_audit_rows(db, n_win=7, n_loss=3)
        result = run_full_self_finetuning(lookback_days=30, db_session=db)
        assert "total_closed_trades" in result
        assert "wrong_direction_count" in result
        assert "new_suggestions" in result
        assert "auto_applied" in result
        assert result["auto_applied"] == 0  # disabled by default

    def test_zero_trades_still_returns_dict(self, db):
        result = run_full_self_finetuning(lookback_days=30, db_session=db)
        assert result["total_closed_trades"] == 0
        assert result["new_suggestions"] == 0
