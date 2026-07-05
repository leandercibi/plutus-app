from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from plutus.api.auth import require_token
from plutus.api.deps import get_app_settings, get_db
from plutus.api.schemas.shared import AiSummaryOut, NewsItemOut, SignalNewsOut
from plutus.config.settings import Settings
from plutus.data.providers.marketaux_provider import build_news_provider
from plutus.data.sectors import resolve_sectors, top_sectors
from plutus.llm.summaries import (
    LLMError,
    SummaryResult,
    generate_daily_summary,
    generate_weekly_summary,
    latest_signal_symbols,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(require_token)])

# In-process TTL cache for live news: the Marketaux free tier is ~100 req/day, so
# we serve repeat homepage loads from cache and only hit the API every ~15 min.
_NEWS_TTL_SECONDS = 900
_news_cache: dict[str, tuple[float, list[NewsItemOut], list[str]]] = {}


def _sentiment_label(score: float | None) -> str:
    if score is None:
        return "neutral"
    if score >= 0.15:
        return "positive"
    if score <= -0.15:
        return "negative"
    return "neutral"


def _to_out(result: SummaryResult) -> AiSummaryOut:
    return AiSummaryOut(
        kind=result.kind,
        cache_key=result.cache_key,
        content=result.content,
        model=result.model,
        created_at=result.created_at,
        cached=result.cached,
        available=result.available,
    )


@router.get("/weekly-summary", response_model=AiSummaryOut)
def weekly_summary(
    force: bool = Query(default=False, description="Bypass cache and regenerate"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> AiSummaryOut:
    """AI narrative of the most recent weekly pipeline run."""
    try:
        return _to_out(generate_weekly_summary(db, settings, force=force))
    except LLMError as exc:
        logger.warning("weekly_summary llm error: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc


@router.get("/daily-summary", response_model=AiSummaryOut)
def daily_summary(
    force: bool = Query(default=False, description="Bypass cache and regenerate"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> AiSummaryOut:
    """AI review of the user's current open holdings."""
    try:
        return _to_out(generate_daily_summary(db, settings, force=force))
    except LLMError as exc:
        logger.warning("daily_summary llm error: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc


@router.get("/signal-news", response_model=SignalNewsOut)
def signal_news(
    force: bool = Query(default=False, description="Bypass the TTL cache and refetch"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SignalNewsOut:
    """Live sector news for the stocks in the current signal list.

    Resolves each top signal symbol to its sector (cached), picks the most
    represented sectors, and pulls recent sector news + sentiment from
    Marketaux. Cached in process for ~15 minutes to respect the free-tier
    request budget.
    """
    from datetime import datetime

    symbols = latest_signal_symbols(db, settings.news_max_symbols)
    provider = build_news_provider(settings)
    if provider is None:
        return SignalNewsOut(
            items=[],
            symbols=symbols,
            sectors=[],
            fetched_at=datetime.utcnow(),
            cached=False,
            available=False,
        )

    cache_key = ",".join(symbols)
    now = time.monotonic()
    if not force and cache_key in _news_cache:
        ts, cached_items, cached_sectors = _news_cache[cache_key]
        if now - ts < _NEWS_TTL_SECONDS:
            return SignalNewsOut(
                items=cached_items,
                symbols=symbols,
                sectors=cached_sectors,
                fetched_at=datetime.utcnow(),
                cached=True,
                available=True,
            )

    sector_map = resolve_sectors(db, symbols, provider)
    sectors = top_sectors(sector_map, settings.news_max_sectors)

    raw = []
    seen_urls: set[str] = set()
    for sector in sectors:
        try:
            fetched = provider.fetch_by_industry(
                sector,
                limit=settings.news_limit,
                lookback_days=settings.news_lookback_days,
                country=settings.news_country,
            )
        except Exception:
            logger.warning("sector news fetch failed for %s", sector, exc_info=True)
            continue
        for it in fetched:
            if it.url and it.url in seen_urls:
                continue  # same article can surface under multiple sectors
            seen_urls.add(it.url)
            raw.append(it)

    items = [
        NewsItemOut(
            symbol=it.symbol,
            title=it.title,
            snippet=it.snippet,
            url=it.url,
            source=it.source,
            published_at=it.published_at,
            sentiment_score=it.sentiment_score,
            sentiment=_sentiment_label(it.sentiment_score),
            sector=it.sector,
        )
        for it in raw
    ]
    # only cache non-empty results so a transient empty fetch isn't pinned for 15 min
    if items:
        _news_cache[cache_key] = (now, items, sectors)

    return SignalNewsOut(
        items=items,
        symbols=symbols,
        sectors=sectors,
        fetched_at=datetime.utcnow(),
        cached=False,
        available=True,
    )
