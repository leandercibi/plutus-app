from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from plutus.config.settings import Settings
from plutus.dashboard.data import (
    CalibrationLineView,
    CalibrationView,
    CandidateView,
    HomeRow,
    HomeView,
    PillarBreakdownView,
    PositionView,
    PostmortemView,
    RunLogRowView,
    SettingsFieldView,
    SettingsView,
    SignalView,
    StrategyLabView,
    TrancheView,
    UserFlowView,
)
from plutus.db import models
from plutus.shared.benchmarks.strip import BenchmarkResult
from plutus.shared.regime.detector import RegimeVerdict
from plutus.shared.risk.cash_position import CashDecision


def _zero_regime() -> RegimeVerdict:
    return RegimeVerdict(label="SIDEWAYS", confidence="low", reasons=["no data"])


def _zero_benchmarks() -> BenchmarkResult:
    return BenchmarkResult(0.0, 0.0, 0.0, 0.0, 0.0, 0)


def load_home(session: Session, settings: Settings | None = None) -> HomeView:
    if settings is None:
        from plutus.config.settings import get_settings
        settings = get_settings()
    regime_row = (
        session.query(models.RegimeSnapshot)
        .order_by(models.RegimeSnapshot.as_of_date.desc())
        .first()
    )
    regime = (
        RegimeVerdict(
            label=regime_row.label,  # type: ignore[arg-type]
            confidence="low",
            breadth_confirmed=regime_row.breadth_confirmed_flip,
        )
        if regime_row
        else _zero_regime()
    )
    open_trades = (
        session.query(models.SwingTrade)
        .filter(models.SwingTrade.state.in_(["OPEN", "T1_HIT"]))
        .all()
    )
    signal_ids = [t.signal_id for t in open_trades]
    signals_by_id: dict[int, models.SwingSignal] = {}
    if signal_ids:
        signals_by_id = {
            s.id: s
            for s in session.query(models.SwingSignal)
            .filter(models.SwingSignal.id.in_(signal_ids))
            .all()
        }
    accum_positions = (
        session.query(models.AccumulationPosition)
        .filter(models.AccumulationPosition.state.in_(["BUILDING", "FULL"]))
        .all()
    )
    accum_tranches: dict[int, list[int]] = {}
    accum_scores: dict[str, int] = {}
    if accum_positions:
        pos_ids = [p.id for p in accum_positions]
        filled = (
            session.query(models.Tranche)
            .filter(
                models.Tranche.position_id.in_(pos_ids),
                models.Tranche.filled_at.isnot(None),
            )
            .all()
        )
        for tr in filled:
            accum_tranches.setdefault(tr.position_id, []).append(tr.seq)
        symbols = [p.symbol for p in accum_positions]
        latest_candidates = (
            session.query(models.AccumulationCandidate)
            .filter(models.AccumulationCandidate.symbol.in_(symbols))
            .order_by(models.AccumulationCandidate.created_at.desc())
            .all()
        )
        for c in latest_candidates:
            accum_scores.setdefault(c.symbol, c.score)
    swing_rows = []
    for t in open_trades[:5]:
        sig = signals_by_id.get(t.signal_id)
        score = sig.score if sig else 0
        bar_pct = min(1.0, t.risk_R / 3.0) if t.risk_R else 0.0
        swing_rows.append(
            HomeRow(
                symbol=t.symbol,
                score=score,
                status=t.state,
                bar_pct=bar_pct,
                detail=f"risk {t.risk_R:.2f}R · {t.qty} shares",
            )
        )
    accum_rows = [
        HomeRow(
            symbol=p.symbol,
            score=accum_scores.get(p.symbol, 0),
            status=p.state,
            bar_pct=len(accum_tranches.get(p.id, [])) / 3.0,
            detail=f"avg ₹{p.avg_cost:.0f} · {p.qty_total} shares",
            tranches_filled=sorted(accum_tranches.get(p.id, [])),
        )
        for p in accum_positions[:5]
    ]
    # Allocated capital: swing = BUY fills on currently-open trades only
    from plutus.db.models import Fill, SwingTrade
    swing_fills = (
        session.query(Fill)
        .join(SwingTrade, Fill.trade_id == SwingTrade.id)
        .filter(SwingTrade.state == "OPEN", Fill.side == "BUY", Fill.kind.in_(["MOCK", "REAL"]))
        .all()
    )
    swing_allocated = sum(Decimal(str(f.qty)) * f.price for f in swing_fills)
    accum_allocated = sum(
        p.avg_cost * Decimal(p.qty_total) for p in accum_positions
    )
    total_capital = Decimal(str(settings.total_capital_inr))
    return HomeView(
        total_capital=total_capital,
        swing_allocated=swing_allocated,
        accumulation_allocated=accum_allocated,
        cash_reserve=max(Decimal("0"), total_capital - swing_allocated - accum_allocated),
        regime=regime,
        cash_decision=CashDecision(deploy_count=len(open_trades), cash_pct_of_pool=0.0, reason=""),
        swing_mode="Active",
        accumulation_mode="Active",
        swing_rows=swing_rows,
        accumulation_rows=accum_rows,
    )


def load_signals(session: Session, limit: int = 50) -> list[SignalView]:
    """Most recent unique signals.

    Bug fix: the dashboard previously LIMIT'd by raw created_at across all
    historical runs, so the same (symbol, bundle) appeared multiple times once
    repeated Sunday runs re-screened the universe. Dedupe by (symbol, bundle)
    keeping the most recent created_at, then slice to `limit`.
    """
    candidate_rows = (
        session.query(models.SwingSignal)
        .order_by(models.SwingSignal.created_at.desc())
        .limit(limit * 10)  # fetch a wider window to dedupe over
        .all()
    )
    seen: set[tuple[str, str]] = set()
    rows: list[models.SwingSignal] = []
    for r in candidate_rows:
        key = (r.symbol, r.bundle)
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
        if len(rows) >= limit:
            break
    out: list[SignalView] = []
    for r in rows:
        pb = r.pillar_breakdown_json or {}
        out.append(
            SignalView(
                id=r.id,
                symbol=r.symbol,
                bundle=r.bundle,
                score=r.score,
                label=r.label,  # type: ignore[arg-type]
                entry=r.entry,
                stop_loss=r.stop_loss,
                target_1=r.target_1,
                target_2=r.target_2,
                pillars=PillarBreakdownView(
                    technical=pb.get("technical", 0),
                    expectancy=pb.get("expectancy", 0),
                    flow=pb.get("flow", 0),
                    sentiment=pb.get("sentiment", 0),
                    regime_fit=pb.get("regime_fit", 0),
                    fundamentals=pb.get("fundamentals", 0),
                ),
                calibration_n=pb.get("calibration_n", 0),
                calibration_band=pb.get("calibration_band", "low"),
                counterfactual=r.counterfactual_text or "",
                delivery_pct=0.0,
                adv_use_pct=0.0,
                circuit_hits_90d=0,
                earnings_in_window=False,
                sector_heat=0.0,
                regime=r.regime_at_signal,
            )
        )
    return out


def load_positions(session: Session) -> list[PositionView]:
    cutoff = datetime.utcnow() - timedelta(days=14)
    rows = (
        session.query(models.SwingTrade)
        .filter(
            (models.SwingTrade.state.in_(["OPEN", "T1_HIT"]))
            | (models.SwingTrade.closed_at >= cutoff)
        )
        .all()
    )
    return [
        PositionView(
            trade_id=t.id,
            symbol=t.symbol,
            bundle=t.bundle,
            age_days=(datetime.utcnow() - t.opened_at).days,
            risk_R=t.risk_R,
            realized_R=t.realized_R or 0.0,
            mfe_R=t.mfe_R or 0.0,
            elapsed_to_t1_pct=0.0,
            trailing_stop=None,
            is_open=t.state in ("OPEN", "T1_HIT"),
            exit_reason=t.exit_reason,
        )
        for t in rows
    ]


def load_candidates(session: Session) -> list[CandidateView]:
    rows = (
        session.query(models.AccumulationCandidate)
        .order_by(models.AccumulationCandidate.created_at.desc())
        .limit(50)
        .all()
    )

    # Index active positions by symbol so we can annotate each candidate
    active_positions = (
        session.query(models.AccumulationPosition)
        .filter(models.AccumulationPosition.state.in_(["BUILDING", "FULL", "PAUSED"]))
        .all()
    )
    pos_by_symbol: dict[str, models.AccumulationPosition] = {
        p.symbol: p for p in active_positions
    }
    # Count filled tranches per position
    filled_counts: dict[int, int] = {}
    if active_positions:
        pos_ids = [p.id for p in active_positions]
        tranches = (
            session.query(models.Tranche)
            .filter(
                models.Tranche.position_id.in_(pos_ids),
                models.Tranche.filled_at.isnot(None),
            )
            .all()
        )
        for t in tranches:
            filled_counts[t.position_id] = filled_counts.get(t.position_id, 0) + 1

    out = []
    for r in rows:
        # Use stored pillar columns when available (Phase 4A+), fall back to derivation
        if r.quality_pillar is not None:
            quality = r.quality_pillar
            growth = r.growth_pillar or 0
            valuation = r.valuation_pillar or 0
            rs_blend = r.rs_pillar or 0
        else:
            rs_avg = (r.rs_30 + r.rs_90 + r.rs_180) / 3.0
            rs_blend = int(round(min(15.0, rs_avg / 100.0 * 15.0)))
            growth = int(round(min(25.0, max(0.0, (r.cagr_eps_3y or 0.0) / 30.0 * 25.0))))
            valuation = int(round(min(30.0, max(0.0, float(r.valuation_pillar_pct or 0) * 30.0))))
            quality = max(0, r.score - rs_blend - growth - valuation)

        hard_avoid_reasons: list[str] = []
        if r.hard_avoid_active:
            hard_avoid_reasons = list(r.hard_avoid_reasons_json or ["hard avoid active"])

        pos = pos_by_symbol.get(r.symbol)
        out.append(CandidateView(
            symbol=r.symbol,
            label=r.label or "WATCH",
            quality=quality,
            growth=growth,
            valuation=valuation,
            rs_blend=rs_blend,
            rs_30=r.rs_30,
            rs_90=r.rs_90,
            rs_180=r.rs_180,
            cagr_eps_3y=r.cagr_eps_3y or 0.0,
            cagr_eps_5y=r.cagr_eps_5y or 0.0,
            valuation_capped=valuation >= 30,
            hard_avoid_reasons=hard_avoid_reasons,
            position_id=pos.id if pos else None,
            tranches_filled=filled_counts.get(pos.id, 0) if pos else 0,
            total_tranches=5,
        ))
    return out


def load_tranches(session: Session) -> list[TrancheView]:
    positions = (
        session.query(models.AccumulationPosition)
        .filter(models.AccumulationPosition.state.in_(["BUILDING", "FULL", "PAUSED"]))
        .all()
    )
    out: list[TrancheView] = []
    for p in positions:
        filled = [
            t.seq
            for t in session.query(models.Tranche)
            .filter_by(position_id=p.id)
            .filter(models.Tranche.filled_at.isnot(None))
            .all()
        ]
        out.append(
            TrancheView(
                position_id=p.id,
                symbol=p.symbol,
                seqs_filled=filled,
                total_tranches=5,
                avg_cost=p.avg_cost,
                pct_gain_loss=0.0,
                last_thesis_check=p.last_thesis_check_at.strftime("%Y-%m-%d"),
                last_thesis_result="ok",
                paused=p.state == "PAUSED",
                paused_reason=p.paused_reason,
            )
        )
    return out


def load_calibration(session: Session, settings: Settings) -> CalibrationView:
    rows = session.query(models.CalibrationRow).order_by(models.CalibrationRow.bucket).all()
    lines = [
        CalibrationLineView(
            bucket=r.bucket,
            regime=r.regime,
            n_closed=r.n_closed,
            win_rate=r.win_rate,
            expectancy_R=r.expectancy_R,
            ci_low_R=r.ci_low_R,
            ci_high_R=r.ci_high_R,
            confidence_band=r.confidence_band,  # type: ignore[arg-type]
            sprt_state=r.sprt_state,
        )
        for r in rows
    ]
    return CalibrationView(
        lines=lines, proposals=[], auto_tune_enabled=settings.auto_tune_enabled
    )


def _compute_bundle_rows(session: Session) -> list:
    """Compute per-bundle stats from all closed trades joined to their signals."""
    from collections import defaultdict
    import math
    from plutus.dashboard.data import PostmortemBundleRow

    closed_trades = (
        session.query(models.SwingTrade)
        .filter(models.SwingTrade.state.in_(["CLOSED_WIN", "CLOSED_LOSS"]))
        .all()
    )
    buckets: dict[str, list[float]] = defaultdict(list)
    for trade in closed_trades:
        sig = session.query(models.SwingSignal).filter_by(id=trade.signal_id).first()
        bundle = sig.bundle if sig else "unknown"
        r = float(trade.realized_R) if trade.realized_R is not None else 0.0
        buckets[bundle].append(r)

    rows = []
    for bundle, rs in sorted(buckets.items()):
        n = len(rs)
        wins = sum(1 for r in rs if r > 0)
        win_rate = wins / n if n else 0.0
        exp = sum(rs) / n if n else 0.0
        # Wilson-style CI using normal approx on R values
        std = (sum((r - exp) ** 2 for r in rs) / n) ** 0.5 if n > 1 else 0.0
        margin = 1.96 * std / math.sqrt(n) if n > 1 else std
        rows.append(PostmortemBundleRow(
            bundle=bundle,
            n_trades=n,
            win_rate=win_rate,
            ci_low_R=round(exp - margin, 2),
            ci_high_R=round(exp + margin, 2),
            expectancy_R=round(exp, 2),
        ))
    return rows


def _most_recent_friday() -> str:
    from datetime import date, timedelta
    today = date.today()
    # weekday(): Monday=0 … Friday=4 … Sunday=6
    days_since_friday = (today.weekday() - 4) % 7
    last_friday = today - timedelta(days=days_since_friday)
    return str(last_friday)


def load_postmortem(session: Session) -> PostmortemView:
    latest = (
        session.query(models.WeeklyPostmortem)
        .order_by(models.WeeklyPostmortem.week_ending.desc())
        .first()
    )
    bundle_rows = _compute_bundle_rows(session)
    current_week = _most_recent_friday()
    if latest is None:
        return PostmortemView(
            week_ending=current_week,
            available_weeks=[current_week],
            benchmarks=_zero_benchmarks(),
            bundle_rows=bundle_rows,
            wrong_direction_count=0,
            no_progress_count=0,
            slippage_divergence_bps=None,
        )
    db_weeks = [
        str(r.week_ending)
        for r in session.query(models.WeeklyPostmortem)
        .order_by(models.WeeklyPostmortem.week_ending.desc())
        .limit(52)
        .all()
    ]
    # Always put the current week first; avoid duplicates
    available_weeks = [current_week] + [w for w in db_weeks if w != current_week]
    wrong_dir = session.query(models.SwingTrade).filter_by(exit_reason="WRONG_DIRECTION").count()
    no_prog = session.query(models.SwingTrade).filter_by(exit_reason="NO_PROGRESS").count()
    return PostmortemView(
        week_ending=current_week,
        available_weeks=available_weeks,
        benchmarks=BenchmarkResult(
            plutus_net_pct=latest.swing_return_pct,
            nifty_net_pct=latest.nifty_return_pct,
            regime_switched_net_pct=latest.regime_switched_return_pct,
            random_liquid_net_pct=latest.random_baseline_return_pct,
            plutus_profit_factor=0.0,
            plutus_n_trades=latest.n_swing_trades_closed,
        ),
        bundle_rows=bundle_rows,
        wrong_direction_count=wrong_dir,
        no_progress_count=no_prog,
        slippage_divergence_bps=None,
    )


def load_user_flow(session: Session) -> UserFlowView:
    from plutus.db.models import RunLogRow

    rows = (
        session.query(RunLogRow)
        .order_by(RunLogRow.started_at.desc())
        .limit(20)
        .all()
    )
    return UserFlowView(
        run_log=[
            RunLogRowView(
                job_name=r.job_name,
                started_at=str(r.started_at),
                ended_at=str(r.ended_at) if r.ended_at else None,
                status=r.status,
            )
            for r in rows
        ],
        freshness_ok=True,
        freshness_detail="",
    )


_SETTINGS_WHITELIST: list[tuple[str, bool]] = [
    # (field_name, editable)
    ("total_capital_inr", True),
    ("risk_per_trade_pct", True),
    ("max_concurrent_swing_positions", True),
    ("soft_dead_zone_lower", True),
    ("soft_dead_zone_upper", True),
    ("accumulation_n_tranches", True),
    ("auto_tune_enabled", True),
    ("midweek_mini_screen_enabled", True),
    ("drawdown_governor_trigger_pct", True),
    ("max_portfolio_heat_R", True),
    ("telegram_chat_id", False),
    ("environment", False),
]


def load_settings(settings: Settings) -> SettingsView:
    dump = settings.model_dump()
    fields = []
    for name, editable in _SETTINGS_WHITELIST:
        val = dump.get(name)
        if val is not None or name in dump:
            fields.append(SettingsFieldView(name=name, value=str(val), editable=editable))
    return SettingsView(fields=fields)


def _load_universe_symbols() -> list[str]:
    """Return the universe symbol list — same source the pipeline uses.

    Priority:
      1. scripts/nse500.csv (the seed universe; what `run_pipeline.py` reads)
      2. distinct symbols already in SwingSignal (backstop so the dropdown is
         never empty after at least one run)
    """
    import csv
    from pathlib import Path

    # 1. CSV — bundled as package data under plutus/data/.
    csv_path = Path(__file__).resolve().parents[1] / "data" / "nse500.csv"
    if csv_path.exists():
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            if reader.fieldnames and "symbol" in reader.fieldnames:
                syms = [r["symbol"].strip() for r in reader if r["symbol"].strip()]
                if syms:
                    return sorted(set(syms))
            f.seek(0)
            syms = [
                line.strip()
                for line in f
                if line.strip() and not line.lower().startswith("symbol")
            ]
            if syms:
                return sorted(set(syms))
    return []


def load_strategy_lab(session: Session | None = None) -> StrategyLabView:
    symbols = _load_universe_symbols()
    if not symbols and session is not None:
        rows = (
            session.query(models.SwingSignal.symbol)
            .distinct()
            .order_by(models.SwingSignal.symbol)
            .all()
        )
        symbols = [r[0] for r in rows]
    return StrategyLabView(
        available_bundles=["trend", "breakout", "reversal", "vcp", "composite", "pead", "smc"],
        available_symbols=symbols,
        smc_display_only=True,
    )
