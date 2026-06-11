"""
postmortem.py — Calibration reporting loop (Phase 4.5, Loop 1).

Runs every Sunday before the weekly pipeline. Reads closed TradeOutcomesAudit
rows from the last 30/60/90 days and produces:
  - Realized win rate per score bucket
  - Realized win rate per bundle
  - Realized win rate per regime at signal time
  - Average MFE/MAE per score bucket (catches stop/target miscalibration)
  - Top 5 best calls + top 5 worst calls
  - WRONG_DIRECTION count (headline failure metric)

Returns a CalibrationReport dataclass. Caller decides whether to persist it
or emit it to weekly_runs.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

WIN_OUTCOMES = {"HIT_T1", "HIT_T2"}
LOSS_OUTCOMES = {"STOPPED", "WRONG_DIRECTION", "EXPIRED"}
DIVERGENCE_THRESHOLD = 15.0  # pp divergence that triggers a suggestion
MIN_TRADES_FOR_BUCKET = 5  # minimum n before a bucket is reported


@dataclass
class BucketStats:
    dimension: str  # 'score_bucket' | 'bundle' | 'regime'
    value: str  # e.g. '70-100', 'trend', 'BULL'
    n_trades: int
    win_rate: float  # realized win rate 0.0–1.0
    avg_mfe_pct: float  # average max-favorable-excursion
    avg_mae_pct: float  # average max-adverse-excursion (negative = loss side)
    wrong_direction_count: int

    @property
    def win_rate_pct(self) -> float:
        return round(self.win_rate * 100, 1)


@dataclass
class TradeRecord:
    symbol: str
    outcome: str
    outcome_pct: float
    score_bucket: str
    bundle_used: str
    regime_at_signal: str
    exit_date: Optional[date]


@dataclass
class CalibrationReport:
    report_date: date
    lookback_days: int
    total_closed_trades: int
    wrong_direction_count: int

    score_bucket_stats: List[BucketStats] = field(default_factory=list)
    bundle_stats: List[BucketStats] = field(default_factory=list)
    regime_stats: List[BucketStats] = field(default_factory=list)

    top_best_calls: List[TradeRecord] = field(default_factory=list)
    top_worst_calls: List[TradeRecord] = field(default_factory=list)

    diverging_buckets: List[BucketStats] = field(
        default_factory=list
    )  # candidates for suggestion loop


def _compute_bucket_stats(
    records: List[TradeRecord],
    dimension: str,
    value_fn,
    audit_rows: list,
) -> List[BucketStats]:
    """Group records by a dimension and compute stats."""
    from collections import defaultdict

    groups: Dict[str, List[TradeRecord]] = defaultdict(list)
    row_by_key: Dict[str, list] = defaultdict(list)
    for rec, row in zip(records, audit_rows):
        key = value_fn(rec)
        if key:
            groups[key].append(rec)
            row_by_key[key].append(row)

    stats = []
    for val, recs in groups.items():
        if len(recs) < MIN_TRADES_FOR_BUCKET:
            continue
        wins = sum(1 for r in recs if r.outcome in WIN_OUTCOMES)
        win_rate = wins / len(recs)
        rows = row_by_key[val]
        mfes = [r.mfe_pct for r in rows if r.mfe_pct is not None]
        maes = [r.mae_pct for r in rows if r.mae_pct is not None]
        wrong_dir = sum(1 for r in recs if r.outcome == "WRONG_DIRECTION")
        stats.append(
            BucketStats(
                dimension=dimension,
                value=val,
                n_trades=len(recs),
                win_rate=round(win_rate, 3),
                avg_mfe_pct=round(sum(mfes) / len(mfes), 2) if mfes else 0.0,
                avg_mae_pct=round(sum(maes) / len(maes), 2) if maes else 0.0,
                wrong_direction_count=wrong_dir,
            )
        )
    return sorted(stats, key=lambda s: s.n_trades, reverse=True)


def _find_diverging(
    stats: List[BucketStats], expected_win_rate: float = 0.55
) -> List[BucketStats]:
    """Return buckets where realized win rate diverges from expected by > threshold."""
    return [
        s
        for s in stats
        if s.n_trades >= MIN_TRADES_FOR_BUCKET
        and abs(s.win_rate_pct - expected_win_rate * 100) >= DIVERGENCE_THRESHOLD
    ]


def run_postmortem(
    lookback_days: int = 30,
    db_session=None,
    expected_win_rate: float = 0.55,
) -> CalibrationReport:
    """
    Query closed TradeOutcomesAudit rows from the last `lookback_days` and
    produce a CalibrationReport. No side effects — caller decides what to do
    with the result.
    """
    from plutus.db.models import TradeOutcomesAudit, OutcomeVerdict
    from plutus.db.session import SessionLocal

    ctx = db_session or SessionLocal()
    close_ctx = db_session is None
    try:
        cutoff = date.today() - timedelta(days=lookback_days)
        audit_rows = (
            ctx.query(TradeOutcomesAudit)
            .filter(
                TradeOutcomesAudit.outcome != OutcomeVerdict.PENDING,
                TradeOutcomesAudit.exit_date >= cutoff,
            )
            .order_by(TradeOutcomesAudit.exit_date.desc())
            .all()
        )
    finally:
        if close_ctx:
            ctx.close()

    if not audit_rows:
        return CalibrationReport(
            report_date=date.today(),
            lookback_days=lookback_days,
            total_closed_trades=0,
            wrong_direction_count=0,
        )

    records = [
        TradeRecord(
            symbol=r.symbol,
            outcome=r.outcome.value if hasattr(r.outcome, "value") else str(r.outcome),
            outcome_pct=r.outcome_pct or 0.0,
            score_bucket=r.score_bucket or "unknown",
            bundle_used=r.bundle_used or "unknown",
            regime_at_signal=r.regime_at_signal or "UNKNOWN",
            exit_date=r.exit_date,
        )
        for r in audit_rows
    ]

    wrong_dir_count = sum(1 for rec in records if rec.outcome == "WRONG_DIRECTION")

    bucket_stats = _compute_bucket_stats(
        records,
        "score_bucket",
        lambda r: r.score_bucket,
        audit_rows,
    )
    bundle_stats = _compute_bucket_stats(
        records,
        "bundle",
        lambda r: r.bundle_used.split(",")[0].strip() if r.bundle_used else None,
        audit_rows,
    )
    regime_stats = _compute_bucket_stats(
        records,
        "regime",
        lambda r: r.regime_at_signal,
        audit_rows,
    )

    # Top 5 best / worst calls by outcome_pct
    sorted_by_pct = sorted(records, key=lambda r: r.outcome_pct, reverse=True)
    top_best = sorted_by_pct[:5]
    top_worst = sorted_by_pct[-5:] if len(sorted_by_pct) >= 5 else sorted_by_pct

    diverging = (
        _find_diverging(bucket_stats, expected_win_rate)
        + _find_diverging(bundle_stats, expected_win_rate)
        + _find_diverging(regime_stats, expected_win_rate)
    )

    return CalibrationReport(
        report_date=date.today(),
        lookback_days=lookback_days,
        total_closed_trades=len(records),
        wrong_direction_count=wrong_dir_count,
        score_bucket_stats=bucket_stats,
        bundle_stats=bundle_stats,
        regime_stats=regime_stats,
        top_best_calls=top_best,
        top_worst_calls=top_worst,
        diverging_buckets=diverging,
    )


def format_report(report: CalibrationReport) -> str:
    """Render a CalibrationReport as a markdown string for weekly_runs.md."""
    lines = [
        f"## Calibration Report — {report.report_date} (last {report.lookback_days}d)",
        f"",
        f"**Total closed trades:** {report.total_closed_trades}  ",
        f"**WRONG_DIRECTION count:** {report.wrong_direction_count}",
        f"",
    ]

    def _table(stats: List[BucketStats], title: str) -> None:
        if not stats:
            return
        lines.append(f"### {title}")
        lines.append(f"| Value | n | Win% | MFE% | MAE% | WrongDir |")
        lines.append(f"|---|---|---|---|---|---|")
        for s in stats:
            lines.append(
                f"| {s.value} | {s.n_trades} | {s.win_rate_pct}% "
                f"| {s.avg_mfe_pct:.1f} | {s.avg_mae_pct:.1f} | {s.wrong_direction_count} |"
            )
        lines.append("")

    _table(report.score_bucket_stats, "By Score Bucket")
    _table(report.bundle_stats, "By Bundle")
    _table(report.regime_stats, "By Regime at Signal")

    if report.top_best_calls:
        lines.append("### Top 5 Best Calls")
        for r in report.top_best_calls:
            lines.append(
                f"- {r.symbol} ({r.bundle_used}) → {r.outcome} +{r.outcome_pct:.1f}%"
            )
        lines.append("")

    if report.top_worst_calls:
        lines.append("### Top 5 Worst Calls")
        for r in report.top_worst_calls:
            lines.append(
                f"- {r.symbol} ({r.bundle_used}) → {r.outcome} {r.outcome_pct:.1f}%"
            )
        lines.append("")

    if report.diverging_buckets:
        lines.append(
            f"### ⚠️ Diverging Buckets (>{DIVERGENCE_THRESHOLD:.0f}pp from expected {report.total_closed_trades and 55}%)"
        )
        for s in report.diverging_buckets:
            lines.append(
                f"- [{s.dimension}] {s.value}: {s.win_rate_pct}% win rate "
                f"(n={s.n_trades}) — expected ~55%"
            )
        lines.append("")

    return "\n".join(lines)
