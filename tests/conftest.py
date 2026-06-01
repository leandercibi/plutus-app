"""Shared pytest fixtures for plutus-app tests."""
import os

# Set required env vars BEFORE any imports
os.environ.setdefault("OPENROUTER_API_KEY", "test-api-key-12345")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
os.environ.setdefault("TELEGRAM_CHAT_ID", "-1001234567890")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from plutus.db.session import Base
from plutus.db.models import (
    WeeklyRun, Recommendation, MockPortfolio, PaperTrade,
    Watchlist, NewsEvent, RejectedHeadline, BacktestResult,
    RecommendationVerdict, TradeDirection, TradeStatus,
    TradeExitReason, OutcomeVerdict
)


# ── Database Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_db_engine():
    """Create in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False}  # Allow multi-threaded access for FastAPI TestClient
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="function")
def test_db_session(test_db_engine):
    """Provide a clean database session for each test."""
    Session = sessionmaker(bind=test_db_engine)
    session = Session()
    
    # Clean all tables before test
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    
    yield session
    
    # Clean all tables after test
    session.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()


# ── Config Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set minimal required environment variables for config testing."""
    from plutus.config import get_settings
    get_settings.cache_clear()  # Clear LRU cache
    
    env_vars = {
        "OPENROUTER_API_KEY": "test-api-key-12345",
        "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "TELEGRAM_CHAT_ID": "-1001234567890",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


@pytest.fixture
def invalid_config_env(monkeypatch):
    """Set incomplete environment variables for validation testing."""
    from plutus.config import get_settings
    get_settings.cache_clear()  # Clear LRU cache
    
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


# ── Model Factory Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def weekly_run_factory(test_db_session):
    """Factory to create WeeklyRun instances."""
    counter = [0]
    
    def _create(
        run_date=None,
        market_regime="BULLISH",
        stocks_screened=150,
        stocks_analysed=20,
        total_buy_signals=5,
        total_watch_signals=3,
    ):
        if run_date is None:
            counter[0] += 1
            run_date = date(2026, 5, 1 + counter[0])
        
        run = WeeklyRun(
            run_date=run_date,
            market_regime=market_regime,
            nifty_trend="ABOVE_EMA50",
            strategy_selected='{"trend": 0.4, "breakout": 0.3}',
            stocks_screened=stocks_screened,
            stocks_analysed=stocks_analysed,
            total_buy_signals=total_buy_signals,
            total_watch_signals=total_watch_signals,
            report_md_path="src/reports/weekly/2026-05-31.md",
        )
        test_db_session.add(run)
        test_db_session.commit()
        return run
    
    return _create


@pytest.fixture
def recommendation_factory(test_db_session):
    """Factory to create Recommendation instances."""
    counter = [0]
    
    def _create(
        symbol=None,
        recommendation=RecommendationVerdict.BUY,
        weekly_run_id=None,
        confidence=8.5,
        entry_low=2450.0,
        entry_high=2480.0,
        target1=2650.0,
        target2=2750.0,
        stop_loss=2380.0,
        hold_days_min=5,
        hold_days_max=8,
    ):
        if symbol is None:
            counter[0] += 1
            symbol = f"TEST{counter[0]}"
        
        rec = Recommendation(
            weekly_run_id=weekly_run_id,
            symbol=symbol,
            exchange="NSE",
            recommendation=recommendation,
            confidence=confidence,
            entry_low=entry_low,
            entry_high=entry_high,
            entry_mid=Decimal(str((entry_low + entry_high) / 2)),
            target1=target1,
            target2=target2,
            stop_loss=stop_loss,
            rr_ratio=(target1 - (entry_low + entry_high) / 2) / ((entry_low + entry_high) / 2 - stop_loss),
            hold_days=hold_days_max,
            hold_days_min=hold_days_min,
            hold_days_max=hold_days_max,
            strategy_used="trend",
            technical_score=7.5,
            sentiment_score=8.0,
            smart_money_score=7.0,
            reasoning_text="Strong uptrend with volume confirmation",
            is_on_demand=False,
        )
        test_db_session.add(rec)
        test_db_session.commit()
        return rec
    
    return _create


@pytest.fixture
def mock_portfolio_factory(test_db_session):
    """Factory to create MockPortfolio instances."""
    counter = [0]
    
    def _create(
        name=None,
        initial_capital=100000.0,
        notes="Test portfolio",
    ):
        if name is None:
            counter[0] += 1
            name = f"test_portfolio_{counter[0]}"
        
        portfolio = MockPortfolio(
            name=name,
            initial_capital=initial_capital,
            notes=notes,
        )
        test_db_session.add(portfolio)
        test_db_session.commit()
        return portfolio
    
    return _create


@pytest.fixture
def paper_trade_factory(test_db_session):
    """Factory to create PaperTrade instances."""
    counter = [0]
    
    def _create(
        portfolio_id,
        symbol=None,
        entry_price=2465.0,
        shares=40,
        status=TradeStatus.OPEN,
        exit_price=None,
        exit_reason=None,
    ):
        if symbol is None:
            counter[0] += 1
            symbol = f"TRADE{counter[0]}"
        
        capital_used = entry_price * shares
        realised_pnl = None
        realised_pnl_pct = None
        
        if exit_price is not None:
            realised_pnl = (exit_price - entry_price) * shares
            realised_pnl_pct = (realised_pnl / capital_used) * 100
        
        trade = PaperTrade(
            portfolio_id=portfolio_id,
            symbol=symbol,
            direction=TradeDirection.LONG,
            entry_price=entry_price,
            shares=shares,
            capital_used=capital_used,
            exit_price=exit_price,
            realised_pnl=realised_pnl,
            realised_pnl_pct=realised_pnl_pct,
            status=status,
            exit_reason=exit_reason,
            strategy_used="trend",
        )
        test_db_session.add(trade)
        test_db_session.commit()
        return trade
    
    return _create


# ── OHLCV Fixtures for Strategy Testing ───────────────────────────────────

@pytest.fixture
def sample_ohlcv_uptrend():
    """Generate 100 bars of uptrending OHLCV data with realistic indicators."""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
    
    # Create uptrend with noise
    base_price = 100.0
    trend = np.linspace(0, 30, 100)  # 30% uptrend over 100 days
    noise = np.random.randn(100) * 2
    close = base_price + trend + noise
    
    # OHLC from close
    high = close + np.random.uniform(0.5, 2.0, 100)
    low = close - np.random.uniform(0.5, 2.0, 100)
    open_price = close + np.random.uniform(-1, 1, 100)
    
    # Volume with occasional spikes
    volume = np.random.randint(500_000, 1_500_000, 100)
    volume[::10] = volume[::10] * 2  # Spikes every 10 bars
    
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)
    
    return df


@pytest.fixture
def sample_ohlcv_ranging():
    """Generate 100 bars of ranging/sideways OHLCV data."""
    np.random.seed(43)
    dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
    
    # Sideways with noise
    base_price = 100.0
    noise = np.random.randn(100) * 3
    close = base_price + noise
    
    high = close + np.random.uniform(0.5, 2.0, 100)
    low = close - np.random.uniform(0.5, 2.0, 100)
    open_price = close + np.random.uniform(-1, 1, 100)
    volume = np.random.randint(500_000, 1_000_000, 100)
    
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)
    
    return df


@pytest.fixture
def sample_ohlcv_downtrend():
    """Generate 100 bars of downtrending OHLCV data."""
    np.random.seed(44)
    dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
    
    base_price = 130.0
    trend = np.linspace(0, -30, 100)  # 30% downtrend
    noise = np.random.randn(100) * 2
    close = base_price + trend + noise
    
    high = close + np.random.uniform(0.5, 2.0, 100)
    low = close - np.random.uniform(0.5, 2.0, 100)
    open_price = close + np.random.uniform(-1, 1, 100)
    volume = np.random.randint(500_000, 1_500_000, 100)
    
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)
    
    return df


@pytest.fixture
def sample_ohlcv_insufficient():
    """Generate only 20 bars - insufficient for most strategies."""
    np.random.seed(45)
    dates = pd.date_range(end=datetime.now(), periods=20, freq='D')
    
    close = 100 + np.random.randn(20) * 2
    high = close + np.random.uniform(0.5, 1.5, 20)
    low = close - np.random.uniform(0.5, 1.5, 20)
    open_price = close + np.random.uniform(-1, 1, 20)
    volume = np.random.randint(500_000, 1_000_000, 20)
    
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)
    
    return df


@pytest.fixture
def sample_ohlcv_breakout():
    """Generate data with consolidation followed by breakout."""
    np.random.seed(46)
    dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
    
    # First 70 bars: tight range
    consolidation = 100 + np.random.randn(70) * 1.5
    # Last 30 bars: breakout upward
    breakout = np.linspace(100, 120, 30) + np.random.randn(30) * 2
    close = np.concatenate([consolidation, breakout])
    
    high = close + np.random.uniform(0.5, 2.0, 100)
    low = close - np.random.uniform(0.5, 2.0, 100)
    open_price = close + np.random.uniform(-1, 1, 100)
    
    # Volume surge on breakout
    volume = np.random.randint(500_000, 800_000, 100)
    volume[70:] = np.random.randint(1_500_000, 2_500_000, 30)
    
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)
    
    return df


@pytest.fixture
def sample_ohlcv_reversal():
    """Generate oversold data suitable for reversal strategy."""
    np.random.seed(47)
    dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
    
    # Sharp decline then bounce
    decline = np.linspace(120, 90, 60) + np.random.randn(60) * 2
    bounce = np.linspace(90, 105, 40) + np.random.randn(40) * 1.5
    close = np.concatenate([decline, bounce])
    
    high = close + np.random.uniform(0.5, 2.0, 100)
    low = close - np.random.uniform(0.5, 2.0, 100)
    open_price = close + np.random.uniform(-1, 1, 100)
    volume = np.random.randint(500_000, 1_500_000, 100)
    
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)
    
    return df
