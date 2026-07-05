"""Build AI summaries of the curated Plutus data.

Two summaries power the dashboard homepage widgets:

* ``weekly_pipeline`` — narrates the most recent Sunday pipeline run: the market
  regime it detected, how many signals it produced, the strongest ideas, and
  any errors.
* ``daily_holdings`` — reviews the user's live open positions: how each is
  doing, aggregate P&L, and anything to be cautious about (stops nearby, weak
  regime, outsized losers).

Both gather structured data from the DB, hand a compact JSON payload to the LLM
with a tight instruction, and cache the result in ``ai_summary`` keyed by the
data it describes so we don't re-bill the LLM on every page load.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.config.settings import Settings
from plutus.db.models import (
    AiSummary,
    Notification,
    RegimeSnapshot,
    RunLogRow,
    SwingSignal,
)
from plutus.llm.client import LLMError, build_llm_client

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

WEEKLY_KIND = "weekly_pipeline"
DAILY_KIND = "daily_holdings"

_MAX_SIGNALS = 12
_MAX_POSITIONS = 25


@dataclass
class SummaryResult:
    kind: str
    cache_key: str
    content: str
    model: str
    created_at: datetime
    cached: bool
    available: bool  # False when no LLM API key is configured


# --------------------------------------------------------------------------- #
# Context builders
# --------------------------------------------------------------------------- #


def latest_signal_symbols(db: Session, limit: int) -> list[str]:
    """Top symbols (by score) from the most recent pipeline run, de-duplicated."""
    latest = (
        db.execute(select(SwingSignal).order_by(SwingSignal.created_at.desc()).limit(1))
        .scalars()
        .first()
    )
    if latest is None:
        return []
    rows = (
        db.execute(
            select(SwingSignal.symbol)
            .where(SwingSignal.run_id == latest.run_id)
            .order_by(SwingSignal.score.desc())
        )
        .scalars()
        .all()
    )
    seen: list[str] = []
    for s in rows:
        if s not in seen:
            seen.append(s)
        if len(seen) >= limit:
            break
    return seen


def _latest_regime(db: Session) -> RegimeSnapshot | None:
    return (
        db.execute(select(RegimeSnapshot).order_by(RegimeSnapshot.as_of_date.desc()).limit(1))
        .scalars()
        .first()
    )


def _fetch_signal_news(settings: Settings, symbols: list[str]) -> list[dict]:
    """Best-effort news + sentiment for signal symbols. Empty on no key/error."""
    from plutus.data.providers.marketaux_provider import build_news_provider

    provider = build_news_provider(settings)
    if provider is None or not symbols:
        return []
    picks = symbols[: settings.news_max_symbols]
    try:
        items = provider.fetch_for_symbols(
            picks, limit=settings.news_limit, lookback_days=settings.news_lookback_days
        )
    except Exception:
        logger.warning("news fetch failed", exc_info=True)
        return []
    return [
        {
            "symbol": it.symbol,
            "title": it.title,
            "snippet": it.snippet,
            "source": it.source,
            "published_at": it.published_at,
            "sentiment_score": it.sentiment_score,
        }
        for it in items
    ]


def build_weekly_context(db: Session, settings: Settings) -> tuple[str, dict]:
    """Return (cache_key, payload) describing the latest pipeline run."""
    latest_signal = (
        db.execute(select(SwingSignal).order_by(SwingSignal.created_at.desc()).limit(1))
        .scalars()
        .first()
    )

    regime = _latest_regime(db)
    run_rows = (
        db.execute(select(RunLogRow).order_by(RunLogRow.started_at.desc()).limit(5)).scalars().all()
    )

    signals_payload: list[dict] = []
    run_id = None
    if latest_signal is not None:
        run_id = latest_signal.run_id
        signals = (
            db.execute(
                select(SwingSignal)
                .where(SwingSignal.run_id == run_id)
                .order_by(SwingSignal.score.desc())
                .limit(_MAX_SIGNALS)
            )
            .scalars()
            .all()
        )
        for s in signals:
            signals_payload.append(
                {
                    "symbol": s.symbol,
                    "bundle": s.bundle,
                    "label": s.label,
                    "score": s.score,
                    "entry": float(s.entry),
                    "stop_loss": float(s.stop_loss),
                    "target_1": float(s.target_1),
                    "target_2": float(s.target_2),
                    "expectancy_R": round(s.expectancy_R, 2),
                    "reward_risk": round(s.drawn_rr, 2),
                }
            )

    total_signals = 0
    if run_id is not None:
        total_signals = (
            db.execute(select(SwingSignal).where(SwingSignal.run_id == run_id))
            .scalars()
            .all()
            .__len__()
        )

    runs_payload = [
        {
            "job": r.job_name,
            "status": r.status or "RUNNING",
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "details": r.details_json,
        }
        for r in run_rows
    ]

    news_payload = _fetch_signal_news(settings, [s["symbol"] for s in signals_payload])

    payload = {
        "generated_at_ist": datetime.now(IST).isoformat(),
        "regime": None
        if regime is None
        else {
            "label": regime.label,
            "as_of_date": regime.as_of_date.isoformat(),
            "india_vix": regime.india_vix,
            "pct_above_50dma": round(regime.pct_above_50dma, 1),
            "pct_above_200dma": round(regime.pct_above_200dma, 1),
            "advance_decline": round(regime.advance_decline, 2),
        },
        "run_id": run_id,
        "total_signals_this_run": total_signals,
        "top_signals": signals_payload,
        "recent_runs": runs_payload,
        "news": news_payload,
    }
    cache_key = run_id or (regime.as_of_date.isoformat() if regime else "empty")
    return cache_key, payload


def build_daily_context(db: Session, settings: Settings) -> tuple[str, dict]:
    """Return (cache_key, payload) describing today's live holdings."""
    from plutus.api.shared import compute_portfolio_snapshot

    snapshot = compute_portfolio_snapshot(db, settings)
    regime = _latest_regime(db)

    positions_payload = [
        {
            "symbol": p.symbol,
            "mode": p.mode,
            "qty": p.qty,
            "avg_cost": p.avg_cost,
            "current_price": p.current_price,
            "pnl": p.pnl,
            "pnl_pct": p.pnl_pct,
            "stop_loss": p.stop_loss,
            "sl_distance_pct": p.sl_distance_pct,
        }
        for p in snapshot.positions[:_MAX_POSITIONS]
    ]

    notifications = (
        db.execute(
            select(Notification)
            .where(Notification.dismissed.is_(False))
            .order_by(Notification.created_at.desc())
            .limit(15)
        )
        .scalars()
        .all()
    )
    alerts_payload = [
        {"severity": n.severity, "symbol": n.symbol, "title": n.title, "body": n.body}
        for n in notifications
    ]

    payload = {
        "generated_at_ist": datetime.now(IST).isoformat(),
        "regime": None
        if regime is None
        else {"label": regime.label, "india_vix": regime.india_vix},
        "portfolio": {
            "total_invested": snapshot.total_invested,
            "total_current": snapshot.total_current,
            "total_pnl": snapshot.total_pnl,
            "total_pnl_pct": snapshot.total_pnl_pct,
            "open_positions": len(snapshot.positions),
        },
        "positions": positions_payload,
        "active_alerts": alerts_payload,
    }
    cache_key = datetime.now(IST).date().isoformat()
    return cache_key, payload


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #

_WEEKLY_SYSTEM = (
    "You are the analyst for Plutus, a swing-trading and accumulation screener for "
    "Indian (NSE) equities. Summarise the most recent weekly pipeline run for the "
    "owner of the account. Be concise, factual, and grounded ONLY in the JSON given "
    "— never invent numbers or tickers. Write in clear plain English for an "
    "experienced retail trader.\n\n"
    "Output GitHub-flavoured markdown with these sections, each 1-3 sentences or a "
    "short bullet list:\n"
    "- A one-line **headline** on the market regime and overall tone of the run.\n"
    "- **What ran**: how many signals were produced and the pipeline's health "
    "(mention failures/errors only if present).\n"
    "- **Top ideas**: up to 5 strongest signals as bullets — `SYMBOL (bundle, label)` "
    "with entry, stop and the reward:risk, one clause on why it stands out.\n"
    "- **Watch-outs**: caveats implied by the regime (e.g. high VIX, weak breadth, "
    "BEAR regime → size down). If data is missing say so plainly.\n"
    "- **News watch**: ONLY if the `news` array is non-empty, add up to 3 bullets "
    "tying a headline to a signal symbol, noting sentiment_score direction "
    "(positive/negative/neutral) and why it might matter. Never fabricate news; if "
    "`news` is empty, omit this section entirely.\n"
    "Keep the whole thing under ~230 words. Do not give financial advice or "
    "guarantees; this is a research summary."
)

_DAILY_SYSTEM = (
    "You are the analyst for Plutus, a swing-trading dashboard for Indian (NSE) "
    "equities. Summarise the owner's CURRENT open holdings for a daily check-in. Be "
    "concise, factual, and grounded ONLY in the JSON given — never invent numbers, "
    "tickers, or news. Write in clear plain English for an experienced retail trader.\n\n"
    "Output GitHub-flavoured markdown with these sections:\n"
    "- A one-line **headline** on total unrealised P&L and how the book is doing.\n"
    "- **Position notes**: bullets for the notable holdings — winners, laggards, and "
    "especially any position whose price is close to its stop loss "
    "(`sl_distance_pct` small or negative). Give `SYMBOL`, P&L%, and the key fact.\n"
    "- **Be cautious about**: concrete risks visible in the data — stops within ~3%, "
    "large single-name losses, a BEAR/high-VIX regime, or active alerts. If nothing "
    "stands out, say the book looks calm.\n"
    "If there are no open positions, say so in one line and stop.\n"
    "Keep the whole thing under ~180 words. Do not give buy/sell advice or "
    "guarantees; this is a status summary, not a recommendation."
)


# --------------------------------------------------------------------------- #
# Generation + caching
# --------------------------------------------------------------------------- #


def _get_cached(db: Session, kind: str, cache_key: str) -> AiSummary | None:
    return (
        db.execute(
            select(AiSummary).where(AiSummary.kind == kind, AiSummary.cache_key == cache_key)
        )
        .scalars()
        .first()
    )


def _upsert(db: Session, kind: str, cache_key: str, content: str, model: str) -> AiSummary:
    row = _get_cached(db, kind, cache_key)
    now = datetime.utcnow()
    if row is None:
        row = AiSummary(
            kind=kind, cache_key=cache_key, content=content, model=model, created_at=now
        )
        db.add(row)
    else:
        row.content = content
        row.model = model
        row.created_at = now
    db.flush()
    return row


def _generate(
    db: Session,
    settings: Settings,
    kind: str,
    system: str,
    cache_key: str,
    payload: dict,
    force: bool,
) -> SummaryResult:
    client = build_llm_client(settings)
    if client is None:
        return SummaryResult(
            kind=kind,
            cache_key=cache_key,
            content="",
            model=settings.llm_model,
            created_at=datetime.utcnow(),
            cached=False,
            available=False,
        )

    if not force:
        cached = _get_cached(db, kind, cache_key)
        if cached is not None:
            return SummaryResult(
                kind=kind,
                cache_key=cache_key,
                content=cached.content,
                model=cached.model,
                created_at=cached.created_at,
                cached=True,
                available=True,
            )

    user_msg = "Here is the data as JSON. Summarise it per your instructions.\n\n" + json.dumps(
        payload, default=str
    )
    content = client.chat(system=system, user=user_msg)
    row = _upsert(db, kind, cache_key, content, client.model)
    return SummaryResult(
        kind=kind,
        cache_key=cache_key,
        content=row.content,
        model=row.model,
        created_at=row.created_at,
        cached=False,
        available=True,
    )


def generate_weekly_summary(db: Session, settings: Settings, force: bool = False) -> SummaryResult:
    cache_key, payload = build_weekly_context(db, settings)
    return _generate(db, settings, WEEKLY_KIND, _WEEKLY_SYSTEM, cache_key, payload, force)


def generate_daily_summary(db: Session, settings: Settings, force: bool = False) -> SummaryResult:
    cache_key, payload = build_daily_context(db, settings)
    return _generate(db, settings, DAILY_KIND, _DAILY_SYSTEM, cache_key, payload, force)


__all__ = [
    "LLMError",
    "SummaryResult",
    "generate_daily_summary",
    "generate_weekly_summary",
]
