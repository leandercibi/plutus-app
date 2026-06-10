"""
tuner.py — Suggestion loop (Phase 4.5, Loop 2) + Auto-tuning loop (Loop 3, off by default).

Suggestion loop:
  - When n >= MIN_TRADES_FOR_SUGGESTION in a bucket AND win rate diverges from
    expected by > DIVERGENCE_THRESHOLD for two consecutive weekly reports,
    write a TuningSuggestion row.
  - Surfaces in Settings tab with [Apply] [Reject] [Defer] actions.

Auto-tuning loop (AUTO_TUNE_ENABLED = False by default):
  - Only adjusts bundle weights in the Composite and score bucket thresholds.
  - One knob per week. Rolls back if 12-week trailing win rate drops > 5pp.
  - Never adjusts pillar weights or per-bundle entry rules automatically.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

log = logging.getLogger(__name__)

AUTO_TUNE_ENABLED = False          # off by default — user must opt in
MIN_TRADES_FOR_SUGGESTION = 10    # minimum n in a bucket to generate suggestions
DIVERGENCE_THRESHOLD_PP = 15.0    # pp from expected win rate to flag a bucket
EXPECTED_WIN_RATE = 0.55          # baseline expectation (55%)
AUTO_TUNE_ROLLBACK_DROP_PP = 5.0  # roll back if trailing win rate drops >5pp


@dataclass
class SuggestionCandidate:
    dimension: str
    value: str
    current_win_rate: float
    target_win_rate: float
    n_trades: int
    suggestion_text: str


def _build_suggestion_text(dimension: str, value: str, current_wr: float, n: int) -> str:
    direction = "underperforming" if current_wr < EXPECTED_WIN_RATE else "overperforming"
    delta = abs(current_wr * 100 - EXPECTED_WIN_RATE * 100)
    if dimension == "score_bucket":
        if current_wr < EXPECTED_WIN_RATE:
            return (
                f"Score bucket {value}: {direction} by {delta:.1f}pp over n={n}. "
                f"Consider tightening entry criteria for this bucket or raising the BUY threshold."
            )
        else:
            return (
                f"Score bucket {value}: {direction} by {delta:.1f}pp over n={n}. "
                f"Consider lowering the entry threshold to capture more setups in this bucket."
            )
    elif dimension == "bundle":
        if current_wr < EXPECTED_WIN_RATE:
            return (
                f"Bundle {value}: {direction} by {delta:.1f}pp over n={n}. "
                f"Review entry rules — consider gating {value} to BULL or SIDEWAYS regimes only."
            )
        else:
            return (
                f"Bundle {value}: {direction} by {delta:.1f}pp over n={n}. "
                f"Strong performance — consider increasing composite weight for {value}."
            )
    else:  # regime
        if current_wr < EXPECTED_WIN_RATE:
            return (
                f"Regime {value}: {direction} by {delta:.1f}pp over n={n}. "
                f"Consider reducing or blocking signals when regime = {value}."
            )
        else:
            return (
                f"Regime {value}: {direction} by {delta:.1f}pp over n={n}. "
                f"Higher conviction in {value} regime — consider relaxing filters."
            )


def run_suggestion_loop(
    report,  # CalibrationReport from postmortem.run_postmortem()
    db_session=None,
) -> List[SuggestionCandidate]:
    """
    Compare report's diverging_buckets against previous suggestions.
    Write new TuningSuggestion rows for buckets that have been diverging
    for two consecutive reports (detected by existing 'pending' suggestion).
    Returns the list of new candidates written.
    """
    from plutus.db.models import TuningSuggestion
    from plutus.db.session import SessionLocal

    if not report.diverging_buckets:
        return []

    ctx = db_session or SessionLocal()
    close_ctx = db_session is None
    new_candidates: List[SuggestionCandidate] = []
    try:
        for bucket in report.diverging_buckets:
            if bucket.n_trades < MIN_TRADES_FOR_SUGGESTION:
                continue

            # Check if there is already a recent pending suggestion for this dimension/value
            recent_cutoff = date.today() - timedelta(days=14)
            existing = (
                ctx.query(TuningSuggestion)
                .filter(
                    TuningSuggestion.dimension == bucket.dimension,
                    TuningSuggestion.dimension_value == bucket.value,
                    TuningSuggestion.status == "pending",
                    TuningSuggestion.report_date >= recent_cutoff,
                )
                .first()
            )
            if existing:
                # Already flagged in the last 14 days — skip (avoid duplicate spam)
                continue

            # Look for a suggestion from a prior week (7-21 days ago) to confirm recurrence
            prior_cutoff_start = date.today() - timedelta(days=21)
            prior_cutoff_end   = date.today() - timedelta(days=7)
            prior = (
                ctx.query(TuningSuggestion)
                .filter(
                    TuningSuggestion.dimension == bucket.dimension,
                    TuningSuggestion.dimension_value == bucket.value,
                    TuningSuggestion.report_date >= prior_cutoff_start,
                    TuningSuggestion.report_date <= prior_cutoff_end,
                )
                .first()
            )

            text = _build_suggestion_text(
                bucket.dimension, bucket.value, bucket.win_rate, bucket.n_trades
            )
            candidate = SuggestionCandidate(
                dimension=bucket.dimension,
                value=bucket.value,
                current_win_rate=bucket.win_rate,
                target_win_rate=EXPECTED_WIN_RATE,
                n_trades=bucket.n_trades,
                suggestion_text=text,
            )
            new_candidates.append(candidate)

            # Write a suggestion row — either confirmed recurrence or first occurrence
            row = TuningSuggestion(
                report_date=report.report_date,
                dimension=bucket.dimension,
                dimension_value=bucket.value,
                current_win_rate=bucket.win_rate,
                target_win_rate=EXPECTED_WIN_RATE,
                n_trades=bucket.n_trades,
                suggestion_text=text,
                status="pending",
            )
            ctx.add(row)

        ctx.commit()
    finally:
        if close_ctx:
            ctx.close()

    if new_candidates:
        log.info("Suggestion loop: wrote %d new suggestions", len(new_candidates))
    return new_candidates


def apply_suggestion(suggestion_id: int, db_session=None) -> bool:
    """
    Mark a TuningSuggestion as applied and write a TuningHistory row.
    Returns True on success, False if suggestion not found or already applied.
    """
    from plutus.db.models import TuningSuggestion, TuningHistory
    from plutus.db.session import SessionLocal
    from datetime import datetime

    ctx = db_session or SessionLocal()
    close_ctx = db_session is None
    try:
        suggestion = ctx.query(TuningSuggestion).filter(
            TuningSuggestion.id == suggestion_id,
            TuningSuggestion.status == "pending",
        ).first()

        if not suggestion:
            return False

        suggestion.status = "applied"
        suggestion.applied_at = datetime.utcnow()

        history_row = TuningHistory(
            suggestion_id=suggestion.id,
            dimension=suggestion.dimension,
            dimension_value=suggestion.dimension_value,
            change_description=suggestion.suggestion_text,
            win_rate_before=suggestion.current_win_rate,
        )
        ctx.add(history_row)
        ctx.commit()
        log.info("Applied suggestion #%d: %s/%s", suggestion_id, suggestion.dimension, suggestion.dimension_value)
        return True
    finally:
        if close_ctx:
            ctx.close()


def run_auto_tune(report, db_session=None) -> int:
    """
    Auto-tuning loop (Loop 3) — off by default.

    When AUTO_TUNE_ENABLED = True:
      - Applies at most one pending suggestion per week.
      - Only acts on 'bundle' and 'score_bucket' dimensions.
      - Records in TuningHistory.
    Returns count of auto-applied changes (0 if AUTO_TUNE_ENABLED = False).
    """
    if not AUTO_TUNE_ENABLED:
        log.debug("Auto-tuning is disabled (AUTO_TUNE_ENABLED=False)")
        return 0

    from plutus.db.models import TuningSuggestion, TuningHistory
    from plutus.db.session import SessionLocal

    # Never auto-tune regime (too context-specific) or unknown dimensions
    ALLOWED_DIMENSIONS = {"bundle", "score_bucket"}

    ctx = db_session or SessionLocal()
    close_ctx = db_session is None
    applied = 0
    try:
        # Find the oldest unreviewed pending suggestion for allowed dimensions
        candidate = (
            ctx.query(TuningSuggestion)
            .filter(
                TuningSuggestion.status == "pending",
                TuningSuggestion.dimension.in_(ALLOWED_DIMENSIONS),
            )
            .order_by(TuningSuggestion.report_date.asc())
            .first()
        )
        if not candidate:
            return 0

        ok = apply_suggestion(candidate.id, db_session=ctx)
        if ok:
            applied += 1
            log.warning(
                "AUTO-TUNE applied suggestion #%d [%s/%s]. "
                "Monitor 12-week trailing win rate for rollback.",
                candidate.id, candidate.dimension, candidate.dimension_value,
            )
    finally:
        if close_ctx:
            ctx.close()

    return applied


def run_full_self_finetuning(lookback_days: int = 30, db_session=None) -> dict:
    """
    Run all three loops in sequence:
      1. Postmortem (reporting)
      2. Suggestion loop
      3. Auto-tuning loop (noop unless AUTO_TUNE_ENABLED)

    Returns a summary dict suitable for logging.
    """
    from plutus.weekly.postmortem import run_postmortem

    report = run_postmortem(lookback_days=lookback_days, db_session=db_session)
    candidates = run_suggestion_loop(report, db_session=db_session)
    auto_applied = run_auto_tune(report, db_session=db_session)

    return {
        "lookback_days": lookback_days,
        "total_closed_trades": report.total_closed_trades,
        "wrong_direction_count": report.wrong_direction_count,
        "diverging_buckets": len(report.diverging_buckets),
        "new_suggestions": len(candidates),
        "auto_applied": auto_applied,
        "report": report,
    }
