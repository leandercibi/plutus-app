"""Tests for scheduler jobs (main.py)."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock, call
from datetime import datetime, date, timedelta
import asyncio
import pytz

from plutus.db.models import (
    WeeklyRun,
    Recommendation,
    RecommendationVerdict,
    NewsEvent,
    PaperTrade,
    Watchlist,
    TradeStatus,
    RejectedHeadline,
)
from tests.mocks.telegram import MockPushEndpoint


IST = pytz.timezone("Asia/Kolkata")


# ── Job 1: weekly_pipeline Tests ─────────────────────────────────────────


@pytest.mark.asyncio
@patch("main.get_universe")
@patch("main.run_all_bundles")
@patch("main.run_analysis")
@patch("main._push_to_bot")
@patch("main._write_weekly_report")
async def test_weekly_pipeline_success(
    mock_write_report,
    mock_push,
    mock_run_analysis,
    mock_run_bundles,
    mock_get_universe,
    test_db_session,
):
    """Test successful weekly_pipeline execution."""
    from main import weekly_pipeline

    # Mock universe
    mock_get_universe.return_value = ["RELIANCE", "INFY", "TCS"]

    # Mock bundle results
    mock_bundle_result = MagicMock()
    mock_bundle_result.sharpe_ratio = 1.5
    mock_run_bundles.return_value = {
        "trend": mock_bundle_result,
        "breakout": mock_bundle_result,
        "reversal": mock_bundle_result,
        "smc": mock_bundle_result,
        "composite": mock_bundle_result,
    }

    # Mock analysis results
    mock_run_analysis.return_value = {
        "recommendation": "BUY",
        "confidence": 8.5,
        "entry_zone": [2450.0, 2480.0],
        "targets": [2650.0, 2750.0],
        "stop_loss": 2380.0,
        "risk_reward": 2.5,
        "hold_days_min": 5,
        "hold_days_max": 8,
        "strategy": "trend",
        "reasoning": "Strong uptrend",
    }

    mock_push.return_value = True

    # Patch SessionLocal to use test session
    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        await weekly_pipeline()

    # Verify universe was fetched
    mock_get_universe.assert_called_once()

    # Verify bundles were run for each symbol
    assert mock_run_bundles.call_count == 3

    # Verify analysis was run for top candidates
    assert mock_run_analysis.call_count > 0

    # Verify database writes
    runs = test_db_session.query(WeeklyRun).all()
    assert len(runs) == 1
    assert runs[0].stocks_screened == 3

    recs = test_db_session.query(Recommendation).all()
    assert len(recs) > 0
    assert all(
        r.recommendation in (RecommendationVerdict.BUY, RecommendationVerdict.WATCH)
        for r in recs
    )

    # Verify report was written
    mock_write_report.assert_called_once()

    # Verify push to bot
    mock_push.assert_called_once()
    call_args = mock_push.call_args
    assert call_args[0][0] == "/push/weekly-summary"
    assert "run_id" in call_args[0][1]


@pytest.mark.asyncio
@patch("main.get_universe")
@patch("main.run_all_bundles")
@patch("main._push_to_bot")
async def test_weekly_pipeline_bundle_failure(
    mock_push,
    mock_run_bundles,
    mock_get_universe,
    test_db_session,
):
    """Test weekly_pipeline handles bundle scoring failures gracefully."""
    from main import weekly_pipeline

    mock_get_universe.return_value = ["RELIANCE", "INVALID"]

    # First symbol succeeds, second fails
    def bundle_side_effect(symbol, **kwargs):
        if symbol == "INVALID":
            raise Exception("Bundle scoring failed")
        mock_result = MagicMock()
        mock_result.sharpe_ratio = 1.5
        return {"trend": mock_result}

    mock_run_bundles.side_effect = bundle_side_effect
    mock_push.return_value = True

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        with patch("main.run_analysis") as mock_analysis:
            mock_analysis.return_value = {
                "recommendation": "WATCH",
                "confidence": 6.0,
                "entry_zone": [100, 110],
                "targets": [120, 130],
                "stop_loss": 95,
                "risk_reward": 1.5,
                "hold_days_min": 3,
                "hold_days_max": 7,
                "strategy": "trend",
                "reasoning": "Test",
            }

            await weekly_pipeline()

    # Should complete despite one failure
    runs = test_db_session.query(WeeklyRun).all()
    assert len(runs) == 1


@pytest.mark.asyncio
@patch("main.get_universe")
@patch("main._push_to_bot")
async def test_weekly_pipeline_push_failure(
    mock_push,
    mock_get_universe,
    test_db_session,
):
    """Test weekly_pipeline continues when push to bot fails."""
    from main import weekly_pipeline

    mock_get_universe.return_value = []  # Empty universe for speed
    mock_push.return_value = False  # Push fails

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        await weekly_pipeline()

    # Should complete despite push failure
    runs = test_db_session.query(WeeklyRun).all()
    assert len(runs) == 1


# ── Job 2: weekly_revalidate Tests ───────────────────────────────────────


@pytest.mark.asyncio
@patch("main.fetch_live_price")
@patch("main._push_to_bot")
async def test_weekly_revalidate_gap_past_entry(
    mock_push,
    mock_fetch_price,
    test_db_session,
    weekly_run_factory,
    recommendation_factory,
):
    """Test weekly_revalidate downgrades BUY to WATCH when gapped past entry."""
    from main import weekly_revalidate

    run = weekly_run_factory()
    rec = recommendation_factory(
        symbol="RELIANCE",
        recommendation=RecommendationVerdict.BUY,
        weekly_run_id=run.id,
        entry_high=2480.0,
        stop_loss=2380.0,
    )

    # LTP > entry_high * 1.02
    mock_fetch_price.return_value = 2550.0
    mock_push.return_value = True

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        await weekly_revalidate()

    # Verify downgrade
    test_db_session.refresh(rec)
    assert rec.recommendation == RecommendationVerdict.WATCH
    assert "gapped past entry" in rec.revalidation_note
    assert rec.revalidated_at is not None

    # Verify push
    mock_push.assert_called_once()
    call_args = mock_push.call_args
    assert call_args[0][0] == "/push/revalidation-delta"
    assert len(call_args[0][1]["downgrades"]) == 1


@pytest.mark.asyncio
@patch("main.fetch_live_price")
@patch("main._push_to_bot")
async def test_weekly_revalidate_broke_stop(
    mock_push,
    mock_fetch_price,
    test_db_session,
    weekly_run_factory,
    recommendation_factory,
):
    """Test weekly_revalidate downgrades BUY to AVOID when stop broken."""
    from main import weekly_revalidate

    run = weekly_run_factory()
    rec = recommendation_factory(
        symbol="INFY",
        recommendation=RecommendationVerdict.BUY,
        weekly_run_id=run.id,
        entry_high=1500.0,
        stop_loss=1400.0,
    )

    # LTP < stop_loss
    mock_fetch_price.return_value = 1380.0
    mock_push.return_value = True

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        await weekly_revalidate()

    # Verify downgrade
    test_db_session.refresh(rec)
    assert rec.recommendation == RecommendationVerdict.AVOID
    assert "broke stop pre-entry" in rec.revalidation_note
    assert rec.revalidated_at is not None


@pytest.mark.asyncio
@patch("main.fetch_live_price")
@patch("main._push_to_bot")
async def test_weekly_revalidate_no_change(
    mock_push,
    mock_fetch_price,
    test_db_session,
    weekly_run_factory,
    recommendation_factory,
):
    """Test weekly_revalidate keeps recommendation when price is valid."""
    from main import weekly_revalidate

    run = weekly_run_factory()
    rec = recommendation_factory(
        symbol="TCS",
        recommendation=RecommendationVerdict.BUY,
        weekly_run_id=run.id,
        entry_high=3500.0,
        stop_loss=3300.0,
    )

    # LTP within valid range
    mock_fetch_price.return_value = 3450.0
    mock_push.return_value = True

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        await weekly_revalidate()

    # Verify no downgrade
    test_db_session.refresh(rec)
    assert rec.recommendation == RecommendationVerdict.BUY
    assert rec.revalidated_at is not None

    # Verify push with empty downgrades
    mock_push.assert_called_once()
    call_args = mock_push.call_args
    assert len(call_args[0][1]["downgrades"]) == 0


@pytest.mark.asyncio
@patch("main.fetch_live_price")
async def test_weekly_revalidate_price_fetch_failure(
    mock_fetch_price,
    test_db_session,
    weekly_run_factory,
    recommendation_factory,
):
    """Test weekly_revalidate handles price fetch failures gracefully."""
    from main import weekly_revalidate

    run = weekly_run_factory()
    rec = recommendation_factory(
        symbol="FAIL",
        recommendation=RecommendationVerdict.BUY,
        weekly_run_id=run.id,
    )

    mock_fetch_price.side_effect = Exception("Network error")

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        with patch("main._push_to_bot") as mock_push:
            mock_push.return_value = True
            await weekly_revalidate()

    # Should complete without crashing
    test_db_session.refresh(rec)
    assert rec.recommendation == RecommendationVerdict.BUY  # Unchanged


@pytest.mark.asyncio
@patch("main._push_to_bot")
async def test_weekly_revalidate_no_run(mock_push, test_db_session):
    """Test weekly_revalidate exits early when no run exists."""
    from main import weekly_revalidate

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        await weekly_revalidate()

    # Should not push anything
    mock_push.assert_not_called()


# ── Job 3: news_monitor Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
@patch("main.fetch_news")
@patch("main.classify_news")
@patch("main._push_to_bot")
async def test_news_monitor_material_news(
    mock_push,
    mock_classify,
    mock_fetch_news,
    test_db_session,
):
    """Test news_monitor detects and alerts on material news."""
    from main import news_monitor

    # Add watchlist symbol
    test_db_session.add(Watchlist(symbol="RELIANCE"))
    test_db_session.commit()

    # Mock news fetch
    mock_fetch_news.return_value = [
        {
            "headline": "RELIANCE announces major acquisition",
            "source": "ET",
            "published_at": datetime.utcnow(),
        }
    ]

    # Mock classification as material
    mock_classify.return_value = {
        "is_material": True,
        "sentiment_label": "positive",
    }

    mock_push.return_value = True

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        await news_monitor()

    # Verify news event was created
    events = test_db_session.query(NewsEvent).all()
    assert len(events) == 1
    assert events[0].symbol == "RELIANCE"
    assert events[0].is_material is True
    assert events[0].alert_sent is True

    # Verify push
    mock_push.assert_called_once()
    call_args = mock_push.call_args
    assert call_args[0][0] == "/push/news-alert"


@pytest.mark.asyncio
@patch("main.fetch_news")
@patch("main.classify_news")
async def test_news_monitor_non_material_news(
    mock_classify,
    mock_fetch_news,
    test_db_session,
):
    """Test news_monitor skips non-material news."""
    from main import news_monitor

    test_db_session.add(Watchlist(symbol="INFY"))
    test_db_session.commit()

    mock_fetch_news.return_value = [{"headline": "Minor update", "source": "ET"}]
    mock_classify.return_value = {"is_material": False}

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        with patch("main._push_to_bot") as mock_push:
            await news_monitor()

    # No events should be created
    events = test_db_session.query(NewsEvent).all()
    assert len(events) == 0


@pytest.mark.asyncio
@patch("main.fetch_news")
@patch("main.classify_news")
@patch("main._push_to_bot")
async def test_news_monitor_duplicate_headline(
    mock_push,
    mock_classify,
    mock_fetch_news,
    test_db_session,
):
    """Test news_monitor skips already-alerted headlines."""
    from main import news_monitor

    test_db_session.add(Watchlist(symbol="TCS"))

    # Add existing alerted event
    test_db_session.add(
        NewsEvent(
            symbol="TCS",
            headline="Duplicate headline",
            source="ET",
            published_at=datetime.utcnow(),
            is_material=True,
            alert_sent=True,
        )
    )
    test_db_session.commit()

    mock_fetch_news.return_value = [{"headline": "Duplicate headline", "source": "ET"}]
    mock_classify.return_value = {"is_material": True, "sentiment_label": "positive"}

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        await news_monitor()

    # Should not create duplicate or push
    events = test_db_session.query(NewsEvent).all()
    assert len(events) == 1  # Only the original
    mock_push.assert_not_called()


@pytest.mark.asyncio
@patch("main.fetch_news")
async def test_news_monitor_no_symbols(mock_fetch_news, test_db_session):
    """Test news_monitor exits early when no symbols to monitor."""
    from main import news_monitor

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        await news_monitor()

    # Should not fetch news
    mock_fetch_news.assert_not_called()


@pytest.mark.asyncio
@patch("main.fetch_news")
@patch("main.classify_news")
async def test_news_monitor_includes_open_trades(
    mock_classify,
    mock_fetch_news,
    test_db_session,
    mock_portfolio_factory,
    paper_trade_factory,
):
    """Test news_monitor includes symbols from open paper trades."""
    from main import news_monitor

    portfolio = mock_portfolio_factory()
    paper_trade_factory(
        portfolio_id=portfolio.id,
        symbol="HDFC",
        status=TradeStatus.OPEN,
    )
    test_db_session.commit()

    mock_fetch_news.return_value = []

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        await news_monitor()

    # Should have fetched news for HDFC
    mock_fetch_news.assert_called_once_with("HDFC")


# ── Job 5: cleanup_rejected_headlines Tests ───────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_rejected_headlines(test_db_session, monkeypatch):
    """Test cleanup_rejected_headlines removes old entries."""
    from main import cleanup_rejected_headlines

    monkeypatch.setenv("REJECTED_HEADLINES_RETENTION_DAYS", "30")
    from plutus.config import get_settings

    get_settings.cache_clear()

    # Add old and recent rejected headlines
    old_date = datetime.utcnow() - timedelta(days=35)
    recent_date = datetime.utcnow() - timedelta(days=10)

    test_db_session.add(
        RejectedHeadline(
            symbol="OLD",
            headline="Old headline",
            rejected_at=old_date,
            filter_status="stoplist",
        )
    )
    test_db_session.add(
        RejectedHeadline(
            symbol="RECENT",
            headline="Recent headline",
            rejected_at=recent_date,
            filter_status="stoplist",
        )
    )
    test_db_session.commit()

    with patch("main.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__ = lambda self: test_db_session
        mock_session_local.return_value.__exit__ = lambda self, *args: None

        await cleanup_rejected_headlines()

    # Verify old entry was deleted
    remaining = test_db_session.query(RejectedHeadline).all()
    assert len(remaining) == 1
    assert remaining[0].symbol == "RECENT"


# ── Helper: _push_to_bot Tests ────────────────────────────────────────────


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_push_to_bot_success(mock_client_class):
    """Test _push_to_bot successful request."""
    from main import _push_to_bot

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    mock_client_class.return_value = mock_client

    result = await _push_to_bot("/push/test", {"data": "test"})

    assert result is True
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_push_to_bot_failure(mock_client_class):
    """Test _push_to_bot handles failures gracefully."""
    from main import _push_to_bot

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("Network error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(
        return_value=False
    )  # must be falsy to propagate exception

    mock_client_class.return_value = mock_client

    result = await _push_to_bot("/push/test", {"data": "test"})

    assert result is False  # Should not raise, returns False


# ── Scheduler Build Tests ─────────────────────────────────────────────────


def test_build_scheduler():
    """Test scheduler is built with all 8 jobs."""
    from main import build_scheduler

    scheduler = build_scheduler()
    jobs = scheduler.get_jobs()

    assert len(jobs) == 8

    job_ids = {job.id for job in jobs}
    expected_ids = {
        "weekly_pipeline",
        "weekly_revalidate",
        "news_monitor",
        "self_finetuning",
        "outcome_tracker",
        "rejected_headlines_cleanup",
        "checkpoint_cleanup",
        "alert_monitor",
    }
    assert job_ids == expected_ids


def test_scheduler_job_config():
    """Test scheduler jobs have correct configuration."""
    from main import build_scheduler

    scheduler = build_scheduler()
    jobs = {job.id: job for job in scheduler.get_jobs()}

    # Weekly pipeline - Sun 18:00
    weekly = jobs["weekly_pipeline"]
    assert weekly.max_instances == 1
    assert weekly.coalesce is True

    # Weekly revalidate - Mon 09:10
    revalidate = jobs["weekly_revalidate"]
    assert revalidate.max_instances == 1

    # News monitor - hourly during market hours
    news = jobs["news_monitor"]
    assert news.max_instances == 1

    # Cleanup - daily 03:00
    cleanup = jobs["rejected_headlines_cleanup"]
    assert cleanup.max_instances == 1
