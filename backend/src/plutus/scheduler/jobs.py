from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.alerts.channels import AlertMessage
from plutus.alerts.formatter import AlertFormatter
from plutus.alerts.monitor import AlertMonitor
from plutus.config.settings import Settings
from plutus.data.freshness import FreshnessError, assert_freshness
from plutus.shared.types import BundleSignal
from plutus.swing.entries.monday_revalidation import MondayRevalidation

if TYPE_CHECKING:
    from plutus.data.ohlcv import OHLCVChain

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RevalidationCandidate:
    symbol: str
    entry: Decimal
    monday_open: Decimal
    atr: Decimal
    hard_kill_fires: bool = False


@dataclass(frozen=True)
class JobResult:
    job_name: str
    status: str  # "OK" | "ABORTED"
    kept: list[str] = field(default_factory=list)
    killed: list[tuple[str, str]] = field(default_factory=list)
    aborted_reason: str | None = None


def monday_revalidation_job(
    candidates: list[RevalidationCandidate],
    monitor: AlertMonitor,
    formatter: AlertFormatter,
    settings: Settings,
    now: datetime,
    session: Session,
) -> JobResult:
    """A15 — re-run entry validation on Monday open; emit kept/killed alert."""
    reval = MondayRevalidation(settings)
    kept: list[str] = []
    killed: list[tuple[str, str]] = []
    for c in candidates:
        outcome = reval.reevaluate(
            sunday_signal=cast(BundleSignal, _StubSignal(c.symbol, c.entry)),
            monday_open=c.monday_open,
            atr=c.atr,
            hard_kill_fires=c.hard_kill_fires,
        )
        if outcome.keep:
            kept.append(c.symbol)
        else:
            killed.append((c.symbol, outcome.reason))

    msg = formatter.format_monday_revalidation(kept, killed, now.date())
    monitor.emit(msg, now, session)
    return JobResult("monday_revalidation", "OK", kept=kept, killed=killed)


def daily_freshness_job(
    latest_candle_date: date,
    run_date: date,
    monitor: AlertMonitor,
    settings: Settings,
    now: datetime,
    session: Session,
) -> JobResult:
    """B11 — abort the day's runs and alert URGENT on stale data."""
    try:
        assert_freshness(latest_candle_date, run_date, settings.freshness_assert_enabled)
    except FreshnessError as exc:
        monitor.emit(
            AlertMessage(
                kind="SL_WARNING",
                symbol=None,
                title="DATA FRESHNESS FAILURE",
                body_md=str(exc),
                severity="URGENT",
                deduplication_key=f"FRESHNESS:{run_date.isoformat()}",
            ),
            now,
            session,
        )
        return JobResult("daily_freshness_check", "ABORTED", aborted_reason=str(exc))
    return JobResult("daily_freshness_check", "OK")


def midweek_mini_screen_job(settings: Settings) -> JobResult:
    """B18 — gated by settings.midweek_mini_screen_enabled; no-op when disabled."""
    if not settings.midweek_mini_screen_enabled:
        return JobResult("midweek_mini_screen", "OK", aborted_reason="disabled")
    return JobResult("midweek_mini_screen", "OK")


def daily_delivery_fetch_job(
    session: Session,
    now: datetime,
    provider: Any | None = None,
) -> JobResult:
    """Fetch today's NSE bhavcopy delivery data, upsert into daily_delivery.

    Filtered to the NSE500 universe (not all ~2000 NSE symbols) to keep the table
    small — that's the same universe the Sunday pipeline scores. A day with no
    published bhavcopy (weekend/holiday) is not an error, just nothing to write.
    """
    from plutus.data.providers.nse500 import NSE500_SYMBOLS
    from plutus.data.providers.nse_delivery_provider import NseDeliveryProvider
    from plutus.db.models import DailyDelivery

    if provider is None:
        provider = NseDeliveryProvider()

    as_of = now.date()
    df = provider.fetch_day(as_of)
    if df.empty:
        return JobResult(
            "daily_delivery_fetch", "OK", aborted_reason="no bhavcopy published for this date"
        )

    universe = set(NSE500_SYMBOLS)
    df = df[df["symbol"].isin(universe)]

    existing_rows = {
        row.symbol: row
        for row in session.execute(
            select(DailyDelivery).where(DailyDelivery.as_of_date == as_of)
        ).scalars()
    }
    written = 0
    for record in df.to_dict("records"):
        symbol = str(record["symbol"])
        delivery_qty = int(record["delivery_qty"])
        traded_qty = int(record["traded_qty"])
        delivery_pct = float(record["delivery_pct"])
        existing = existing_rows.get(symbol)
        if existing:
            existing.delivery_qty = delivery_qty
            existing.traded_qty = traded_qty
            existing.delivery_pct = delivery_pct
        else:
            session.add(
                DailyDelivery(
                    symbol=symbol,
                    as_of_date=as_of,
                    delivery_qty=delivery_qty,
                    traded_qty=traded_qty,
                    delivery_pct=delivery_pct,
                )
            )
        written += 1
    session.flush()
    return JobResult("daily_delivery_fetch", "OK", kept=[f"{written} symbols written"])


def sunday_full_run_job(
    universe: list[str],
    ohlcv_chain: OHLCVChain,
    regime_inputs: Any,  # RegimeInputs
    session: Session,
    settings: Settings,
    monitor: AlertMonitor,
    formatter: AlertFormatter,
    now: datetime,
    run_id: str | None = None,
    fundamentals_provider: Any | None = None,
) -> JobResult:
    """Full Sunday pipeline: regime → bundles → accum screener → cull → Telegram digest."""
    from plutus.accumulation.fundamentals.scoring import FundamentalsScorer
    from plutus.data.providers.fundamentals_provider import FundamentalsProvider
    from plutus.db.models import AccumulationCandidate, SwingSignal
    from plutus.shared.cost_model.costs import CostModel
    from plutus.shared.regime.detector import RegimeDetector
    from plutus.shared.regime.snapshot import save_snapshot
    from plutus.shared.rs.blend import RSBlend
    from plutus.shared.scoring_inputs import ExpectancyInputs
    from plutus.swing.bundles.base import BundleContext
    from plutus.swing.bundles.breakout import BreakoutBundle
    from plutus.swing.bundles.composite import CompositeBundle
    from plutus.swing.bundles.reversal import ReversalBundle
    from plutus.swing.bundles.trend import TrendBundle
    from plutus.swing.bundles.vcp import VCPBundle
    from plutus.swing.scoring.classifier import classify
    from plutus.swing.scoring.expectancy import compute_expectancy
    from plutus.swing.scoring.flow_pillar import flow_score_from_history
    from plutus.swing.scoring.fundamentals_avoid import (
        evaluate_fundamentals_avoid,
        fundamentals_score,
    )
    from plutus.swing.scoring.pillars import technical_score
    from plutus.swing.scoring.watch_signal import (
        _delivery_df_from_db,
        _FallbackCalibration,
        _make_watch_signal,
    )

    run_id = run_id or str(uuid.uuid4())[:8]
    today = now.date()
    start = today - timedelta(days=365)

    if fundamentals_provider is None:
        fundamentals_provider = FundamentalsProvider()

    # 1. Regime
    verdict = RegimeDetector(settings).classify(regime_inputs)
    save_snapshot(today, verdict, regime_inputs, session)
    session.flush()

    calibration = _FallbackCalibration()
    cost_model = CostModel(settings)
    rs_blend_engine = RSBlend()
    fund_scorer = FundamentalsScorer(settings)
    bundles = [
        TrendBundle(settings),
        BreakoutBundle(settings),
        ReversalBundle(settings),
        VCPBundle(settings),
    ]

    _REGIME_PILLAR: dict[str, int] = {
        "BULL": 15,
        "SOFT_BULL": 10,
        "NEUTRAL": 7,
        "SOFT_BEAR": 3,
        "BEAR": 0,
    }

    # 2. Pre-fetch Nifty candles once for RSBlend
    nifty_df: pd.DataFrame | None = None
    try:
        nifty_result = ohlcv_chain.fetch("^NSEI", start, today)
        if nifty_result.success and nifty_result.df is not None and not nifty_result.df.empty:
            nifty_df = nifty_result.df.copy()
            nifty_df.columns = [c.lower() for c in nifty_df.columns]
            if "date" not in nifty_df.columns:
                nifty_df = nifty_df.reset_index()
                nifty_df.rename(columns={nifty_df.columns[0]: "date"}, inplace=True)
            logger.info("Nifty fetched: %d candles", len(nifty_df))
    except Exception as exc:
        logger.warning("Nifty fetch failed, RS blend will be zero: %s", exc)

    # 3. Per-symbol loop — collect all candidates before any DB writes
    pending_signals: list[SwingSignal] = []
    pending_accum: list[AccumulationCandidate] = []

    for symbol in universe:
        try:
            result = ohlcv_chain.fetch(symbol, start, today)
            if not result.success or result.df is None or result.df.empty:
                continue
            candles = result.df.copy()
            candles.columns = [c.lower() for c in candles.columns]
            if "date" not in candles.columns:
                candles = candles.reset_index()
                candles.rename(columns={candles.columns[0]: "date"}, inplace=True)

            delivery_df = _delivery_df_from_db(symbol, session, today)
            flow_score = flow_score_from_history(delivery_df)

            # v4: compute the new pillars once per symbol (cheap; shared by watch + bundle paths).
            from plutus.swing.scoring.composite_v4 import compute_v4_pillars

            v4_pillars = compute_v4_pillars(
                candles=candles,
                delivery_df=delivery_df,
                nifty_df=nifty_df,
                regime_inputs=regime_inputs,
                rs_engine=rs_blend_engine,
                settings=settings,
            )

            # Fetch once per symbol — shared by both the watch-screen and bundle scoring
            # paths below. D/E is a hard veto (dangerously leveraged non-financial
            # companies); ROCE + valuation contribute a graded 0-10 fundamentals score.
            fund = fundamentals_provider.fetch(symbol)
            fund_avoid = evaluate_fundamentals_avoid(fund.de, fund.is_financial, settings)
            fund_score = fundamentals_score(fund.roce, fund.pe_ttm)

            # — Swing path —
            symbol_signals: list[SwingSignal] = []

            ws = _make_watch_signal(
                symbol,
                candles,
                verdict.label,
                run_id,
                now,
                cost_model,
                calibration,
                settings,
                v4_pillars=v4_pillars,
                fundamentals_hard_avoid=fund_avoid.avoid,
                fundamentals_pts=fund_score,
                flow_pts=flow_score,
            )
            if ws is not None:
                symbol_signals.append(ws)

            ctx = BundleContext(symbol=symbol, regime=verdict.label, delivery=delivery_df)
            sub_signals = []
            for bundle in bundles:
                try:
                    sig = bundle.fit_signal(symbol, candles, ctx)
                    if sig is not None:
                        sub_signals.append(sig)
                except Exception as exc:
                    logger.error("bundle %s failed for %s: %s", bundle.name, symbol, exc)

            comp_ctx = BundleContext(
                symbol=symbol,
                regime=verdict.label,
                delivery=delivery_df,
                extras={"sub_signals": sub_signals},
            )
            try:
                comp = CompositeBundle(calibration, verdict.label).fit_signal(
                    symbol, candles, comp_ctx
                )
                if comp is not None:
                    sub_signals.append(comp)
            except Exception as exc:
                logger.error("composite failed for %s: %s", symbol, exc)

            for sig in sub_signals:
                try:
                    from plutus.swing.scoring.composite_v4 import (
                        composite_score as _composite_v4,
                    )
                    from plutus.swing.scoring.composite_v4 import (
                        legacy_regime_pillar,
                        pillar_breakdown,
                    )

                    tech = technical_score(candles)
                    risk = sig.entry - sig.stop_loss
                    if risk <= 0:
                        continue
                    exp = compute_expectancy(
                        ExpectancyInputs(
                            bundle=sig.bundle,
                            regime=verdict.label,
                            entry=sig.entry,
                            stop_loss=sig.stop_loss,
                            target_1=sig.target_1,
                            target_2=sig.target_2,
                            qty=1,
                        ),
                        calibration,
                        cost_model,
                        settings,
                    )
                    band = calibration.confidence_band(sig.bundle, verdict.label, "")
                    exp_pillar = int(round(min(25.0, max(0.0, exp.expectancy_R / 2.0 * 25.0))))

                    if settings.enable_v4_selection:
                        regime_pillar = v4_pillars.regime_pts
                        rs_pts = v4_pillars.rs_pts
                        flow_pts = v4_pillars.flow_pts
                        composite_score = _composite_v4(
                            technical_pts=tech.total,
                            expectancy_pts=exp_pillar,
                            regime_pts=regime_pillar,
                            rs_pts=rs_pts,
                            flow_pts=flow_pts,
                        )
                        breakdown = pillar_breakdown(
                            technical_pts=tech.total,
                            expectancy_pts=exp_pillar,
                            regime_pts=regime_pillar,
                            v4=v4_pillars,
                            calibration_band=band,
                            calibration_n=calibration.n_for(sig.bundle, verdict.label),
                            extras={"tradable": composite_score >= settings.score_floor_actionable},
                        )
                    else:
                        regime_pillar = legacy_regime_pillar(verdict.label)
                        composite_score = (
                            tech.total + exp_pillar + regime_pillar + fund_score + flow_score
                        )
                        breakdown = {
                            "technical": tech.total,
                            "expectancy": exp_pillar,
                            "flow": flow_score,
                            "sentiment": 0,
                            "regime_fit": regime_pillar,
                            "fundamentals": fund_score,
                            "calibration_band": band,
                            "calibration_n": calibration.n_for(sig.bundle, verdict.label),
                        }

                    cls_out = classify(
                        score=composite_score,
                        expectancy=exp,
                        calibration_band=band,
                        settings=settings,
                        hard_avoid=fund_avoid.avoid,
                    )
                    if cls_out.label == "AVOID":
                        continue

                    drawn_rr = float((sig.target_1 - sig.entry) / risk)
                    symbol_signals.append(
                        SwingSignal(
                            run_id=run_id,
                            symbol=sig.symbol,
                            bundle=sig.bundle,
                            score=composite_score,
                            label=cls_out.label,
                            entry=sig.entry,
                            stop_loss=sig.stop_loss,
                            target_1=sig.target_1,
                            target_2=sig.target_2,
                            expectancy_R=exp.expectancy_R,
                            drawn_rr=drawn_rr,
                            regime_at_signal=verdict.label,
                            pillar_breakdown_json=breakdown,
                            counterfactual_text=cls_out.counterfactual,
                            created_at=now,
                        )
                    )
                except Exception as exc:
                    logger.error("signal scoring failed for %s/%s: %s", symbol, sig.bundle, exc)

            # If any bundle fired, drop the lighter watch_screen signal for this symbol
            bundle_sigs = [s for s in symbol_signals if s.bundle != "watch_screen"]
            if bundle_sigs:
                symbol_signals = bundle_sigs
            pending_signals.extend(symbol_signals)

            # — Accumulation path —
            try:
                accum = _run_accum_screener(
                    symbol=symbol,
                    candles=candles,
                    nifty_df=nifty_df,
                    rs_blend_engine=rs_blend_engine,
                    fund_scorer=fund_scorer,
                    fund_provider=fundamentals_provider,
                    verdict_label=verdict.label,
                    settings=settings,
                    run_id=run_id,
                    now=now,
                )
                if accum is not None:
                    pending_accum.append(accum)
            except Exception as exc:
                logger.error("accum screener failed for %s: %s", symbol, exc)

        except Exception as exc:
            logger.error("per-symbol pipeline failed for %s: %s", symbol, exc)

    # 4. Cull: top 15 swing signals, top 10 accumulation candidates (by composite score)
    top_swing = sorted(pending_signals, key=lambda s: s.score, reverse=True)[:15]
    top_accum = sorted(pending_accum, key=lambda c: c.score, reverse=True)[:10]

    for swing_sig in top_swing:
        session.add(swing_sig)
    for cand in top_accum:
        session.add(cand)

    session.flush()

    # 5. Calibration update from closed trade history
    try:
        _update_calibration(session, settings, now)
    except Exception as exc:
        logger.error("calibration update failed: %s", exc)

    buy_count = sum(1 for s in top_swing if s.label == "BUY")
    buy_watch_count = sum(1 for s in top_swing if s.label == "BUY_WATCH")
    total = len(top_swing)

    monitor.emit(
        AlertMessage(
            kind="ENTRY",
            symbol=None,
            title="Sunday run complete",
            body_md=(
                f"Regime: *{verdict.label}* ({verdict.confidence})\n"
                f"Signals: {buy_count} BUY · {buy_watch_count} BUY\\_WATCH\n"
                f"Accum candidates: {len(top_accum)}\n"
                f"run\\_id: {run_id}"
            ),
            severity="INFO",
            deduplication_key=f"SUNDAY_RUN:{today.isoformat()}",
        ),
        now,
        session,
    )
    return JobResult("sunday_full_run", "OK", kept=[f"{total} signals", f"{len(top_accum)} accum"])


def daily_exit_monitor_job(
    session: Session,
    settings: Settings,
    monitor: AlertMonitor,
    formatter: AlertFormatter,
    now: datetime,
    ohlcv_chain: OHLCVChain | None = None,
    current_prices: dict[str, Decimal] | None = None,
) -> JobResult:
    """Check all open trades; emit SL_BREACH / T1_HIT alerts when triggered."""
    from plutus.db.models import SwingSignal, SwingTrade

    open_trades = (
        session.execute(select(SwingTrade).where(SwingTrade.state.in_(["OPEN", "T1_HIT"])))
        .scalars()
        .all()
    )
    if not open_trades:
        return JobResult("daily_exit_monitor", "OK")

    prices: dict[str, Decimal] = {}
    if ohlcv_chain is not None:
        today = now.date()
        start = today - timedelta(days=5)
        for sym in {t.symbol for t in open_trades}:
            try:
                r = ohlcv_chain.fetch(sym, start, today)
                if r.success and r.df is not None and not r.df.empty:
                    prices[sym] = Decimal(str(float(r.df["close"].iloc[-1])))
            except Exception as exc:
                logger.error("price fetch failed", extra={"symbol": sym, "error": str(exc)})
    if current_prices:
        prices.update(current_prices)

    if not prices:
        return JobResult("daily_exit_monitor", "OK", aborted_reason="no prices")

    for trade in open_trades:
        price = prices.get(trade.symbol)
        if price is None:
            continue
        signal = session.get(SwingSignal, trade.signal_id)
        if signal is None:
            continue
        try:
            if price <= signal.stop_loss and trade.state == "OPEN":
                trade.state = "CLOSED_LOSS"
                trade.closed_at = now
                trade.exit_reason = "SL_BREACH"
                trade.realized_R = float((price - signal.entry) / (signal.entry - signal.stop_loss))
                monitor.emit(
                    formatter.format_sl_breach(trade.symbol, price, now.date()),
                    now,
                    session,
                )
            elif price >= signal.target_1 and trade.state == "OPEN":
                trade.state = "T1_HIT"
                monitor.emit(
                    formatter.format_t1_hit(trade.symbol, now.date()),
                    now,
                    session,
                )
        except Exception as exc:
            logger.error("exit check failed", extra={"symbol": trade.symbol, "error": str(exc)})

    session.flush()
    return JobResult("daily_exit_monitor", "OK")


def _run_accum_screener(
    symbol: str,
    candles: pd.DataFrame,
    nifty_df: pd.DataFrame | None,
    rs_blend_engine: Any,
    fund_scorer: Any,
    fund_provider: Any,
    verdict_label: str,
    settings: Settings,
    run_id: str,
    now: datetime,
) -> Any | None:
    """Full accumulation screener for one symbol.

    Returns an unsaved AccumulationCandidate or None when:
      - fewer than 200 candles (RSBlend needs 180 days of history)
      - fundamentals fetch raises
      - hard_avoid is active (still returned so the dashboard shows the flag)
    """
    from plutus.accumulation.fundamentals.hard_avoid import FundamentalsSnapshot
    from plutus.accumulation.fundamentals.valuation import Valuation, ValuationInputs
    from plutus.db.models import AccumulationCandidate
    from plutus.shared.rs.blend import RSBlendResult

    if len(candles) < 200:
        return None

    # RS blend vs Nifty
    rs_result: RSBlendResult
    if nifty_df is not None and len(nifty_df) >= 181:
        try:
            rs_result = rs_blend_engine.compute(candles, nifty_df)
        except Exception as exc:
            logger.debug("RSBlend failed for %s: %s", symbol, exc)
            rs_result = RSBlendResult(rs_30=0.0, rs_90=0.0, rs_180=0.0, blended=0.0)
    else:
        rs_result = RSBlendResult(rs_30=0.0, rs_90=0.0, rs_180=0.0, blended=0.0)

    # Fundamentals fetch
    try:
        fund = fund_provider.fetch(symbol)
    except Exception as exc:
        logger.warning("fundamentals fetch failed for %s: %s", symbol, exc)
        return None

    snapshot = FundamentalsSnapshot(
        de=fund.de,
        is_financial=fund.is_financial,
        last_eps_yoy_change=_last_eps_yoy(fund.eps_history),
        improving_guidance=False,
        going_concern_flag=False,
        promoter_pledge_increase_pp=0.0,
        roce=fund.roce,
        fcf_margin=fund.fcf_margin,
        pe_ttm=fund.pe_ttm or 0.0,
    )
    val_inputs = ValuationInputs(
        pe_ttm=fund.pe_ttm or 0.0,
        pe_5y_median=fund.pe_5y_median or fund.pe_ttm or 0.0,
        ev_ebitda=fund.ev_ebitda or 0.0,
        earnings_history_5y=fund.eps_history,
    )

    fs = fund_scorer.score(snapshot, val_inputs, fund.eps_history, rs_result)
    pillars = fs.pillars

    val_obj = Valuation()
    cagr_3y = val_obj.cagr_eps(fund.eps_history, years=4)
    cagr_5y = val_obj.cagr_eps(fund.eps_history, years=5)

    thesis = (
        f"{symbol}: {fs.label} | {verdict_label} | "
        f"Q={pillars.quality}/30 G={pillars.growth}/25 "
        f"V={pillars.valuation}/30 RS={pillars.relative_strength}/15 | "
        f"Total={pillars.total}/100"
    )

    return AccumulationCandidate(
        run_id=run_id,
        symbol=symbol,
        score=pillars.total,
        label=fs.label,
        rs_30=rs_result.rs_30,
        rs_90=rs_result.rs_90,
        rs_180=rs_result.rs_180,
        quality_pillar=pillars.quality,
        growth_pillar=pillars.growth,
        valuation_pillar=pillars.valuation,
        rs_pillar=pillars.relative_strength,
        cagr_eps_3y=None if cagr_3y is None else round(cagr_3y * 100, 1),
        cagr_eps_5y=None if cagr_5y is None else round(cagr_5y * 100, 1),
        valuation_pillar_pct=pillars.valuation / 30.0,
        thesis_text=thesis,
        hard_avoid_active=fs.hard_avoid.avoid,
        hard_avoid_reasons_json=list(fs.hard_avoid.reasons),
        created_at=now,
    )


def _last_eps_yoy(eps_history: pd.DataFrame) -> float:
    """YoY change in EPS from the last two fiscal years (fractional: -0.6 = -60%)."""
    if eps_history.empty or len(eps_history) < 2:
        return 0.0
    ordered = eps_history.sort_values("year")
    prev = float(ordered["eps"].iloc[-2])
    curr = float(ordered["eps"].iloc[-1])
    if prev <= 0:
        return 0.0
    return (curr - prev) / prev


def _update_calibration(session: Session, settings: Settings, now: datetime) -> None:
    """Scan closed swing trades and upsert CalibrationRow stats per (bundle, regime).

    Uses Wilson 95% CI for win_rate and derives R-unit bounds assuming
    average win ≈ 1.5R and average loss ≈ 1R. SPRT state is a simple
    accept/continue/reject based on the sample win_rate.
    """
    import math
    from collections import defaultdict

    from plutus.db.models import CalibrationRow, SwingSignal, SwingTrade

    closed_rows = (
        session.query(SwingTrade, SwingSignal)
        .join(SwingSignal, SwingTrade.signal_id == SwingSignal.id)
        .filter(
            SwingTrade.state.in_(["CLOSED_WIN", "CLOSED_LOSS"]),
            SwingTrade.realized_R.isnot(None),
        )
        .all()
    )

    if not closed_rows:
        return

    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for trade, signal in closed_rows:
        groups[(signal.bundle, signal.regime_at_signal)].append(float(trade.realized_R))

    for (bucket, regime), r_vals in groups.items():
        n = len(r_vals)
        n_wins = sum(1 for r in r_vals if r > 0)
        win_rate = n_wins / n
        exp_R = sum(r_vals) / n

        # Wilson 95% CI on win_rate, converted to R-unit bounds
        z = 1.96
        denom = 1.0 + z * z / n
        p_hat = win_rate
        centre = (p_hat + z * z / (2 * n)) / denom
        margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n)) / denom
        wr_low = max(0.0, centre - margin)
        wr_high = min(1.0, centre + margin)
        ci_low_R = min(wr_low * 1.5 - (1 - wr_low) * 1.0, exp_R)
        ci_high_R = max(wr_high * 1.5 - (1 - wr_high) * 1.0, exp_R)

        if n >= settings.calibration_min_n_high:
            band = "high"
        elif n >= settings.calibration_min_n_low:
            band = "medium"
        else:
            band = "low"

        if win_rate > 0.55 and n >= settings.calibration_min_n_low:
            sprt = "accept_H1"
        elif win_rate < 0.40 and n >= settings.calibration_min_n_low:
            sprt = "accept_H0"
        else:
            sprt = "continue"

        existing = session.query(CalibrationRow).filter_by(bucket=bucket, regime=regime).first()
        if existing is not None:
            existing.n_closed = n
            existing.win_rate = win_rate
            existing.expectancy_R = exp_R
            existing.ci_low_R = ci_low_R
            existing.ci_high_R = ci_high_R
            existing.sprt_state = sprt
            existing.confidence_band = band
            existing.last_updated = now
        else:
            session.add(
                CalibrationRow(
                    bucket=bucket,
                    regime=regime,
                    n_closed=n,
                    win_rate=win_rate,
                    expectancy_R=exp_R,
                    ci_low_R=ci_low_R,
                    ci_high_R=ci_high_R,
                    sprt_state=sprt,
                    confidence_band=band,
                    last_updated=now,
                )
            )

    logger.info(
        "Calibration updated: %d buckets from %d closed trades", len(groups), len(closed_rows)
    )


@dataclass(frozen=True)
class _StubSignal:
    symbol: str
    entry: Decimal


# ---------------------------------------------------------------------------
# Full pipeline jobs called by scheduler/runner.py
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SundayResult:
    run_id: str
    signals_written: int
    kept: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
