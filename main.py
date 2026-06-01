from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime
from pathlib import Path

import httpx
import pytz
import structlog
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from sqlalchemy import text

from plutus.agents.graph import run_analysis
from plutus.api.routes import router as api_router
from plutus.backtesting.runner import run_all_bundles
from plutus.config import settings
from plutus.data.news import classify_news, fetch_news
from plutus.data.ohlcv import fetch_live_price, fetch_ohlcv
from plutus.data.universe import get_universe
from plutus.db.models import (
    NewsEvent,
    PaperTrade,
    Recommendation,
    TradeStatus,
    Watchlist,
    WeeklyRun,
)
from plutus.db.session import SessionLocal
# from plutus.weekly.outcomes import track_recommendation_outcomes  # see 14_weekly_history.md

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="Plutus — Main", version="1.0.0")
app.include_router(api_router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": "plutus-main"}


# ── Helper: push to plutus-bot over loopback ────────────────────────────────

async def _push_to_bot(path: str, payload: dict) -> bool:
    """POST to plutus-bot's loopback /push endpoint. Never raises."""
    url = f"http://{settings.BOT_INTERNAL_HOST}:{settings.BOT_INTERNAL_PORT}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.post(url, json=payload)
            r.raise_for_status()
        return True
    except Exception as e:
        logger.warning("bot_push_failed", url=url, error=str(e))
        return False


# ── Job 1: weekly_pipeline (Sun 18:00 IST) ──────────────────────────────────

async def weekly_pipeline() -> None:
    """
    Full Sunday research run.

    1. Fetch universe via get_universe() (≈150-200 symbols after liquidity filters).
    2. For each symbol, run all 5 strategy bundles; score by best Sharpe.
    3. Pick top 20 by best-bundle Sharpe.
    4. For each top-20 symbol, run run_analysis() with cache disabled (fresh).
    5. Insert 1 weekly_runs row + N recommendations rows.
    6. Write src/reports/weekly/<YYYY-MM-DD>.md.
    7. Push run_id to plutus-bot for Telegram summary fan-out.
    """
    started = datetime.now(IST)
    run_date = started.date()
    logger.info("weekly_pipeline_start", date=str(run_date))

    # 1. Universe
    symbols = await asyncio.to_thread(get_universe)
    logger.info("universe_ready", count=len(symbols))

    # 2. All 5 bundles per symbol — Backtrader is sync, push to thread pool.
    def _score_symbol(sym: str) -> tuple[str, float, dict]:
        bundle_results = run_all_bundles(sym, lookback_days=settings.BACKTEST_LOOKBACK_DAYS)
        # bundle_results: Dict[str, BundleResult] with 5 keys
        best_name, best = max(
            bundle_results.items(),
            key=lambda kv: (kv[1].sharpe_ratio if kv[1] else -999),
        )
        return sym, best.sharpe_ratio, {n: r for n, r in bundle_results.items()}

    scored: list[tuple[str, float, dict]] = []
    for sym in symbols:
        try:
            scored.append(await asyncio.to_thread(_score_symbol, sym))
        except Exception as e:
            logger.warning("bundle_scoring_failed", symbol=sym, error=str(e))

    # 3. Top 20 by best-bundle Sharpe
    scored.sort(key=lambda t: t[1], reverse=True)
    top20 = scored[: settings.BACKTEST_TOP_CANDIDATES]
    logger.info("top_candidates_selected", count=len(top20))

    # 4. Fresh agent run per top-20 (cache disabled)
    analyses: list[tuple[str, dict]] = []
    for sym, _sharpe, _bundles in top20:
        try:
            result = await asyncio.to_thread(run_analysis, sym, "NSE", False)
            #                                                  ^^^^^ use_cache=False
            analyses.append((sym, result))
        except Exception as e:
            logger.error("agent_pipeline_failed", symbol=sym, error=str(e))

    # 5. DB writes — one weekly_runs + one recommendations row per BUY/WATCH
    buy_list: list[str] = []
    watch_list: list[str] = []
    with SessionLocal() as db:
        wr = WeeklyRun(
            run_date=run_date,
            stocks_screened=len(symbols),
            stocks_analysed=len(top20),
            generated_at=started,
        )
        db.add(wr)
        db.flush()

        for sym, res in analyses:
            verdict = res.get("recommendation")
            if verdict not in ("BUY", "WATCH"):
                continue
            entry_zone = res.get("entry_zone") or [None, None]
            targets = res.get("targets") or [None, None]
            entry_low = entry_zone[0]
            entry_high = entry_zone[1]
            entry_mid = (
                (float(entry_low) + float(entry_high)) / 2.0
                if entry_low is not None and entry_high is not None
                else None
            )
            hold_min = res.get("hold_days_min")
            hold_max = res.get("hold_days_max")

            db.add(
                Recommendation(
                    weekly_run_id=wr.id,
                    symbol=sym,
                    exchange="NSE",
                    recommendation=verdict,
                    confidence=res.get("confidence"),
                    entry_low=entry_low,
                    entry_high=entry_high,
                    entry_mid=entry_mid,
                    target1=targets[0] if targets else None,
                    target2=targets[1] if len(targets) > 1 else None,
                    stop_loss=res.get("stop_loss"),
                    rr_ratio=res.get("risk_reward"),
                    hold_days_min=hold_min,
                    hold_days_max=hold_max,
                    hold_days=hold_max,  # backwards-compat alias
                    strategy_used=res.get("strategy"),
                    reasoning_text=res.get("reasoning"),
                    is_on_demand=False,
                )
            )
            (buy_list if verdict == "BUY" else watch_list).append(sym)

        wr.total_buy_signals = len(buy_list)
        wr.total_watch_signals = len(watch_list)
        report_path = f"{settings.REPORTS_DIR}/{run_date}.md"
        wr.report_md_path = report_path
        db.commit()
        run_id = wr.id

    # 6. Markdown report
    await asyncio.to_thread(_write_weekly_report, run_date, analyses, report_path)

    # 7. Telegram fan-out via plutus-bot loopback push.
    ok = await _push_to_bot("/push/weekly-summary", {"run_id": run_id})
    if not ok:
        logger.warning("weekly_summary_push_skipped", run_id=run_id)

    elapsed = (datetime.now(IST) - started).total_seconds()
    logger.info(
        "weekly_pipeline_complete",
        run_id=run_id,
        buy=len(buy_list),
        watch=len(watch_list),
        elapsed_s=int(elapsed),
    )


def _write_weekly_report(run_date: date, analyses: list[tuple[str, dict]], path: str) -> None:
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    buys = [(s, r) for s, r in analyses if r.get("recommendation") == "BUY"]
    watches = [(s, r) for s, r in analyses if r.get("recommendation") == "WATCH"]

    lines: list[str] = [
        f"# Weekly Analysis — {run_date.strftime('%d %B %Y')}",
        "",
        f"**Generated:** {datetime.now(IST).strftime('%d %b %Y %H:%M')} IST",
        "",
        "---",
        "",
        f"## BUY Signals ({len(buys)})",
        "",
    ]
    for sym, r in buys:
        ez = r.get("entry_zone") or [0, 0]
        tg = r.get("targets") or [0, 0]
        lines += [
            f"### {sym}",
            f"- **Confidence:** {r.get('confidence', 0):.1f}/10",
            f"- **Entry Zone:** ₹{ez[0]:.0f} – ₹{ez[1]:.0f}",
            f"- **Target 1:** ₹{tg[0]:.0f} | **Target 2:** ₹{tg[1]:.0f}",
            f"- **Stop Loss:** ₹{r.get('stop_loss', 0):.0f}",
            f"- **R:R:** {r.get('risk_reward', 0):.2f}",
            f"- **Strategy:** {r.get('strategy', 'N/A')}",
            f"- **Reasoning:** {r.get('reasoning', '')}",
            f"- **Outcome:** PENDING",
            "",
        ]
    if watches:
        lines += [f"## WATCH ({len(watches)})", ""]
        for sym, r in watches:
            lines += [f"- **{sym}** — {(r.get('reasoning') or '')[:200]}", ""]

    with open(path, "w") as f:
        f.write("\n".join(lines))


# ── Job 2: weekly_revalidate (Mon 09:10 IST) ────────────────────────────────

async def weekly_revalidate() -> None:
    """
    Monday-open gap re-validation. NO LLM CALLS. Pure price math.

    For each BUY / WATCH recommendation in the latest weekly_run:
      - LTP > entry_high * 1.02  → BUY → WATCH (note: 'gapped past entry')
      - LTP < stop_loss          → BUY → AVOID (note: 'broke stop pre-entry')
      - else                     → unchanged
    Then push a single delta message to plutus-bot.
    """
    logger.info("weekly_revalidate_start")

    downgraded: list[tuple[str, str, str, float]] = []  # (sym, from, to, ltp)
    with SessionLocal() as db:
        latest = (
            db.query(WeeklyRun).order_by(WeeklyRun.run_date.desc()).first()
        )
        if latest is None:
            logger.info("weekly_revalidate_no_run")
            return

        recs = (
            db.query(Recommendation)
            .filter(
                Recommendation.weekly_run_id == latest.id,
                Recommendation.recommendation.in_(("BUY", "WATCH")),
            )
            .all()
        )

        now_ist = datetime.now(IST)
        for rec in recs:
            try:
                ltp = await asyncio.to_thread(fetch_live_price, rec.symbol)
            except Exception as e:
                logger.warning("revalidate_price_failed", symbol=rec.symbol, error=str(e))
                continue

            new_verdict = rec.recommendation
            note: str | None = None

            entry_high = float(rec.entry_high) if rec.entry_high is not None else None
            stop = float(rec.stop_loss) if rec.stop_loss is not None else None

            if rec.recommendation == "BUY" and entry_high and ltp > entry_high * 1.02:
                new_verdict = "WATCH"
                gap_pct = (ltp - entry_high) / entry_high * 100
                note = f"gapped past entry +{gap_pct:.1f}% (LTP ₹{ltp:.2f})"
            elif rec.recommendation == "BUY" and stop and ltp < stop:
                new_verdict = "AVOID"
                note = f"broke stop pre-entry (LTP ₹{ltp:.2f} < SL ₹{stop:.2f})"

            rec.revalidated_at = now_ist
            if new_verdict != rec.recommendation:
                downgraded.append((rec.symbol, rec.recommendation, new_verdict, ltp))
                rec.recommendation = new_verdict
                rec.revalidation_note = note

        db.commit()

    logger.info("weekly_revalidate_done", downgraded=len(downgraded))

    # Single delta message via plutus-bot push (bot composes the human text).
    payload = {
        "run_id": latest.id,
        "downgrades": [
            {"symbol": s, "from": f, "to": t, "ltp": ltp}
            for (s, f, t, ltp) in downgraded
        ],
    }
    await _push_to_bot("/push/revalidation-delta", payload)


# ── Job 3: news_monitor (Mon-Fri hourly, 09:00–15:59 IST) ───────────────────

async def news_monitor() -> None:
    """
    Hourly news scan during market hours.

    Symbols scanned = watchlist UNION open paper-trade symbols.
    For each symbol:
      headlines = fetch_news(sym)
      result = classify_news(sym, headlines)   # applies hard prefilter,
                                                # persists rejected to rejected_headlines,
                                                # only LLM-calls on survivors
      if result['is_material'] and not already alerted on this headline:
          insert news_events row (alert_sent=False)
          push to plutus-bot; on success flip alert_sent=True
    """
    logger.info("news_monitor_start")

    # 1. Build symbol set
    with SessionLocal() as db:
        watch_syms = {w.symbol for w in db.query(Watchlist).all()}
        open_syms = {
            t.symbol
            for t in db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.OPEN).all()
        }
    symbols = sorted(watch_syms | open_syms)
    if not symbols:
        logger.info("news_monitor_no_symbols")
        return

    checked = 0
    alerted = 0
    for sym in symbols:
        try:
            headlines = await asyncio.to_thread(fetch_news, sym)
            if not headlines:
                continue
            result = await asyncio.to_thread(classify_news, sym, headlines)
            checked += 1
            if not result.get("is_material"):
                continue

            top = headlines[0]["headline"]
            with SessionLocal() as db:
                already = (
                    db.query(NewsEvent)
                    .filter(
                        NewsEvent.symbol == sym,
                        NewsEvent.headline == top,
                        NewsEvent.alert_sent.is_(True),
                    )
                    .first()
                )
                if already:
                    continue

                evt = NewsEvent(
                    symbol=sym,
                    headline=top,
                    source=headlines[0].get("source", ""),
                    published_at=datetime.utcnow(),
                    sentiment=result.get("sentiment_label"),
                    is_material=True,
                    alert_sent=False,
                )
                db.add(evt)
                db.commit()
                event_id = evt.id

            ok = await _push_to_bot("/push/news-alert", {"event_id": event_id})
            if ok:
                with SessionLocal() as db:
                    db.query(NewsEvent).filter(NewsEvent.id == event_id).update(
                        {NewsEvent.alert_sent: True}
                    )
                    db.commit()
                alerted += 1
        except Exception as e:
            logger.error("news_monitor_symbol_failed", symbol=sym, error=str(e))

    logger.info("news_monitor_done", symbols=len(symbols), classified=checked, alerted=alerted)


# ── Job 4: outcome_tracker (Mon-Fri 16:30 IST) ──────────────────────────────
#
# `track_recommendation_outcomes` lives in `plutus/weekly/outcomes.py` and is
# the canonical implementation per `14_weekly_history.md` — IST trading days,
# stop-first ambiguity rule, fill = entry_mid. We simply schedule it here.


# ── Job 5: cleanup_rejected_headlines (Daily 03:00 IST) ─────────────────────

async def cleanup_rejected_headlines() -> None:
    """
    Daily prune of rejected_headlines older than
    settings.REJECTED_HEADLINES_RETENTION_DAYS (default 30).
    """
    days = int(settings.REJECTED_HEADLINES_RETENTION_DAYS)
    sql = text(
        "DELETE FROM rejected_headlines "
        "WHERE rejected_at < NOW() - (:days || ' days')::interval"
    )
    with SessionLocal() as db:
        result = db.execute(sql, {"days": days})
        deleted = result.rowcount or 0
        db.commit()
    logger.info("rejected_headlines_cleaned", deleted=deleted, retention_days=days)


# ── Scheduler wiring ────────────────────────────────────────────────────────

def build_scheduler() -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=IST)

    # 1. Weekly research run — Sun 18:00 IST.
    sched.add_job(
        weekly_pipeline,
        CronTrigger(
            day_of_week=settings.WEEKLY_RUN_DAY,           # "sun"
            hour=settings.WEEKLY_RUN_HOUR,                 # 18
            minute=settings.WEEKLY_RUN_MINUTE,             # 0
            timezone=IST,
        ),
        id="weekly_pipeline",
        name="Weekly research run (Sun 18:00 IST)",
        max_instances=1,
        coalesce=True,
    )

    # 2. Monday gap re-validation — Mon 09:10 IST.
    sched.add_job(
        weekly_revalidate,
        CronTrigger(day_of_week="mon", hour=9, minute=10, timezone=IST),
        id="weekly_revalidate",
        name="Monday-open gap re-validation",
        max_instances=1,
        coalesce=True,
    )

    # 3. Hourly news monitor — Mon-Fri 09:00-15:59 IST, every 60 min.
    sched.add_job(
        news_monitor,
        CronTrigger(
            day_of_week="mon-fri",
            hour=f"{settings.MARKET_OPEN_HOUR}-{settings.MARKET_CLOSE_HOUR - 1}",
            minute=f"*/{settings.NEWS_CHECK_INTERVAL_MINUTES}",
            timezone=IST,
        ),
        id="news_monitor",
        name="Hourly news scan (Mon-Fri, market hours)",
        max_instances=1,
    )

    # 4. Outcome tracker — Mon-Fri 16:30 IST (TODO: Phase 7 - track_recommendation_outcomes not implemented yet)
    # sched.add_job(
    #     track_recommendation_outcomes,
    #     CronTrigger(day_of_week="mon-fri", hour=16, minute=30, timezone=IST),
    #     id="outcome_tracker",
    #     name="Daily outcome tracker",
    #     max_instances=1,
    #     coalesce=True,
    # )

    # 5. rejected_headlines cleanup — Daily 03:00 IST.
    sched.add_job(
        cleanup_rejected_headlines,
        CronTrigger(hour=3, minute=0, timezone=IST),
        id="rejected_headlines_cleanup",
        name="Daily rejected_headlines retention prune",
        max_instances=1,
        coalesce=True,
    )

    return sched


# ── Entry point ─────────────────────────────────────────────────────────────

async def _serve() -> None:
    sched = build_scheduler()
    sched.start()
    logger.info(
        "plutus_main_starting",
        api_host=settings.API_HOST,
        api_port=settings.API_PORT,
        jobs=[j.id for j in sched.get_jobs()],
    )

    config = uvicorn.Config(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        loop="asyncio",
        log_config=None,
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        sched.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(_serve())
