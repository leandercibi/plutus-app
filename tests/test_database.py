"""Tests for Plutus database models and session management."""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal

from plutus.db.models import (
    WeeklyRun, Recommendation, MockPortfolio, PaperTrade,
    Watchlist, NewsEvent, RejectedHeadline, BacktestResult,
    RecommendationVerdict, TradeDirection, TradeStatus,
    TradeExitReason, OutcomeVerdict
)


class TestWeeklyRunModel:
    """Test WeeklyRun model creation and relationships."""
    
    def test_create_weekly_run(self, test_db_session):
        """Test creating a WeeklyRun instance."""
        run = WeeklyRun(
            run_date=date(2026, 5, 25),
            market_regime="BULLISH",
            nifty_trend="ABOVE_EMA50",
            strategy_selected='{"trend": 0.4, "breakout": 0.3}',
            stocks_screened=150,
            stocks_analysed=20,
            total_buy_signals=5,
            total_watch_signals=3,
            report_md_path="src/reports/weekly/2026-05-25.md",
        )
        test_db_session.add(run)
        test_db_session.commit()
        
        assert run.id is not None
        assert run.run_date == date(2026, 5, 25)
        assert run.market_regime == "BULLISH"
        assert run.stocks_screened == 150
    
    def test_weekly_run_multiple_runs_same_date_allowed(self, test_db_session):
        """Test that multiple runs on the same date are now allowed (scheduled + manual)."""
        run1 = WeeklyRun(run_date=date(2026, 5, 25), run_type="scheduled", stocks_screened=100)
        run2 = WeeklyRun(run_date=date(2026, 5, 25), run_type="manual", stocks_screened=150)
        test_db_session.add_all([run1, run2])
        test_db_session.commit()
        assert run1.id != run2.id
    
    def test_weekly_run_recommendations_relationship(self, weekly_run_factory, recommendation_factory):
        """Test one-to-many relationship with recommendations."""
        run = weekly_run_factory()
        rec1 = recommendation_factory(weekly_run_id=run.id, symbol="RELIANCE")
        rec2 = recommendation_factory(weekly_run_id=run.id, symbol="TCS")
        
        assert len(run.recommendations) == 2
        assert rec1 in run.recommendations
        assert rec2 in run.recommendations


class TestRecommendationModel:
    """Test Recommendation model creation and relationships."""
    
    def test_create_recommendation(self, test_db_session):
        """Test creating a Recommendation instance."""
        rec = Recommendation(
            symbol="RELIANCE",
            exchange="NSE",
            recommendation=RecommendationVerdict.BUY,
            confidence=8.5,
            entry_low=2450.0,
            entry_high=2480.0,
            entry_mid=Decimal("2465.00"),
            target1=2650.0,
            target2=2750.0,
            stop_loss=2380.0,
            rr_ratio=2.5,
            hold_days=8,
            hold_days_min=5,
            hold_days_max=8,
            strategy_used="trend",
            technical_score=7.5,
            sentiment_score=8.0,
            smart_money_score=7.0,
            reasoning_text="Strong uptrend",
        )
        test_db_session.add(rec)
        test_db_session.commit()
        
        assert rec.id is not None
        assert rec.symbol == "RELIANCE"
        assert rec.recommendation == RecommendationVerdict.BUY
        assert rec.outcome == OutcomeVerdict.PENDING
    
    def test_recommendation_with_weekly_run(self, weekly_run_factory, test_db_session):
        """Test recommendation linked to weekly run."""
        run = weekly_run_factory()
        
        rec = Recommendation(
            weekly_run_id=run.id,
            symbol="TCS",
            recommendation=RecommendationVerdict.WATCH,
            entry_low=3500.0,
            entry_high=3550.0,
            entry_mid=Decimal("3525.00"),
        )
        test_db_session.add(rec)
        test_db_session.commit()
        
        assert rec.weekly_run_id == run.id
        assert rec.weekly_run == run
    
    def test_recommendation_on_demand(self, test_db_session):
        """Test on-demand recommendation (no weekly_run_id)."""
        rec = Recommendation(
            symbol="INFY",
            recommendation=RecommendationVerdict.BUY,
            is_on_demand=True,
            entry_low=1400.0,
            entry_high=1420.0,
            entry_mid=Decimal("1410.00"),
        )
        test_db_session.add(rec)
        test_db_session.commit()
        
        assert rec.weekly_run_id is None
        assert rec.is_on_demand is True
    
    def test_recommendation_verdict_enum(self, test_db_session):
        """Test all RecommendationVerdict enum values."""
        verdicts = [
            RecommendationVerdict.BUY,
            RecommendationVerdict.SELL,
            RecommendationVerdict.HOLD,
            RecommendationVerdict.WATCH,
            RecommendationVerdict.AVOID,
        ]
        
        for verdict in verdicts:
            rec = Recommendation(
                symbol=f"TEST_{verdict.value}",
                recommendation=verdict,
                entry_low=100.0,
                entry_high=110.0,
                entry_mid=Decimal("105.00"),
            )
            test_db_session.add(rec)
        
        test_db_session.commit()
        
        saved_recs = test_db_session.query(Recommendation).all()
        assert len(saved_recs) == 5
    
    def test_recommendation_outcome_tracking(self, recommendation_factory, test_db_session):
        """Test outcome tracking fields."""
        rec = recommendation_factory()
        
        rec.outcome = OutcomeVerdict.HIT_T1
        rec.outcome_pct = 7.5
        rec.outcome_fill_price = Decimal("2465.00")
        rec.outcome_exit_price = Decimal("2650.00")
        rec.outcome_exit_date = date.today()
        rec.outcome_tracked_at = datetime.utcnow()
        
        test_db_session.commit()
        
        assert rec.outcome == OutcomeVerdict.HIT_T1
        assert rec.outcome_pct == 7.5
    
    def test_recommendation_revalidation(self, recommendation_factory, test_db_session):
        """Test revalidation fields."""
        rec = recommendation_factory()
        
        rec.revalidation_note = "gapped past entry"
        rec.revalidated_at = datetime.utcnow()
        
        test_db_session.commit()
        
        assert rec.revalidation_note == "gapped past entry"
        assert rec.revalidated_at is not None


class TestMockPortfolioModel:
    """Test MockPortfolio model and computed properties."""
    
    def test_create_mock_portfolio(self, test_db_session):
        """Test creating a MockPortfolio instance."""
        portfolio = MockPortfolio(
            name="aggressive_momentum",
            initial_capital=100000.0,
            notes="Test portfolio for momentum strategies",
        )
        test_db_session.add(portfolio)
        test_db_session.commit()
        
        assert portfolio.id is not None
        assert portfolio.name == "aggressive_momentum"
        assert portfolio.initial_capital == 100000.0
    
    def test_portfolio_unique_name_constraint(self, test_db_session):
        """Test that portfolio name must be unique."""
        p1 = MockPortfolio(name="test_portfolio", initial_capital=100000.0)
        test_db_session.add(p1)
        test_db_session.commit()
        
        p2 = MockPortfolio(name="test_portfolio", initial_capital=200000.0)
        test_db_session.add(p2)
        
        with pytest.raises(Exception):  # IntegrityError
            test_db_session.commit()
    
    def test_portfolio_current_cash_no_trades(self, mock_portfolio_factory):
        """Test current_cash property with no trades."""
        portfolio = mock_portfolio_factory(initial_capital=100000.0)
        
        assert portfolio.current_cash == 100000.0
    
    def test_portfolio_current_cash_with_open_trades(self, mock_portfolio_factory, paper_trade_factory):
        """Test current_cash property with open trades."""
        portfolio = mock_portfolio_factory(initial_capital=100000.0)
        
        # Open trade: 40 shares @ 2465 = 98,600
        paper_trade_factory(
            portfolio_id=portfolio.id,
            entry_price=2465.0,
            shares=40,
            status=TradeStatus.OPEN,
        )
        
        # Current cash = 100,000 - 98,600 = 1,400
        assert portfolio.current_cash == 1400.0
    
    def test_portfolio_current_cash_with_closed_trades(self, mock_portfolio_factory, paper_trade_factory):
        """Test current_cash property with closed trades."""
        portfolio = mock_portfolio_factory(initial_capital=100000.0)
        
        # Closed trade: profit of 7,400
        paper_trade_factory(
            portfolio_id=portfolio.id,
            entry_price=2465.0,
            shares=40,
            exit_price=2650.0,
            status=TradeStatus.CLOSED,
        )
        
        # Current cash = 100,000 + 7,400 = 107,400
        assert portfolio.current_cash == 107400.0
    
    def test_portfolio_total_realised_pnl(self, mock_portfolio_factory, paper_trade_factory):
        """Test total_realised_pnl property."""
        portfolio = mock_portfolio_factory(initial_capital=100000.0)
        
        # Trade 1: profit
        paper_trade_factory(
            portfolio_id=portfolio.id,
            entry_price=2465.0,
            shares=40,
            exit_price=2650.0,
            status=TradeStatus.CLOSED,
        )
        
        # Trade 2: loss
        paper_trade_factory(
            portfolio_id=portfolio.id,
            symbol="TCS",
            entry_price=3500.0,
            shares=20,
            exit_price=3400.0,
            status=TradeStatus.CLOSED,
        )
        
        # Total PnL = (2650-2465)*40 + (3400-3500)*20 = 7400 - 2000 = 5400
        assert portfolio.total_realised_pnl == 5400.0
    
    def test_portfolio_win_rate_no_trades(self, mock_portfolio_factory):
        """Test win_rate property with no trades."""
        portfolio = mock_portfolio_factory()
        
        assert portfolio.win_rate == 0.0
    
    def test_portfolio_win_rate_calculation(self, mock_portfolio_factory, paper_trade_factory):
        """Test win_rate property calculation."""
        portfolio = mock_portfolio_factory(initial_capital=100000.0)
        
        # 2 winning trades
        paper_trade_factory(
            portfolio_id=portfolio.id,
            entry_price=2465.0,
            shares=40,
            exit_price=2650.0,
            status=TradeStatus.CLOSED,
        )
        paper_trade_factory(
            portfolio_id=portfolio.id,
            symbol="TCS",
            entry_price=3500.0,
            shares=20,
            exit_price=3600.0,
            status=TradeStatus.CLOSED,
        )
        
        # 1 losing trade
        paper_trade_factory(
            portfolio_id=portfolio.id,
            symbol="INFY",
            entry_price=1400.0,
            shares=50,
            exit_price=1350.0,
            status=TradeStatus.CLOSED,
        )
        
        # Win rate = 2/3 * 100 = 66.67%
        assert abs(portfolio.win_rate - 66.67) < 0.1


class TestPaperTradeModel:
    """Test PaperTrade model creation and calculations."""
    
    def test_create_paper_trade(self, mock_portfolio_factory, test_db_session):
        """Test creating a PaperTrade instance."""
        portfolio = mock_portfolio_factory()
        
        trade = PaperTrade(
            portfolio_id=portfolio.id,
            symbol="RELIANCE",
            direction=TradeDirection.LONG,
            entry_price=2465.0,
            shares=40,
            capital_used=98600.0,
            status=TradeStatus.OPEN,
        )
        test_db_session.add(trade)
        test_db_session.commit()
        
        assert trade.id is not None
        assert trade.symbol == "RELIANCE"
        assert trade.status == TradeStatus.OPEN
    
    def test_paper_trade_with_recommendation(self, mock_portfolio_factory, recommendation_factory, test_db_session):
        """Test paper trade linked to recommendation."""
        portfolio = mock_portfolio_factory()
        rec = recommendation_factory()
        
        trade = PaperTrade(
            portfolio_id=portfolio.id,
            linked_recommendation_id=rec.id,
            symbol=rec.symbol,
            entry_price=2465.0,
            shares=40,
            capital_used=98600.0,
        )
        test_db_session.add(trade)
        test_db_session.commit()
        
        assert trade.linked_recommendation_id == rec.id
        assert trade.recommendation == rec
    
    def test_paper_trade_closed_with_profit(self, mock_portfolio_factory, test_db_session):
        """Test closed trade with profit calculation."""
        portfolio = mock_portfolio_factory()
        
        trade = PaperTrade(
            portfolio_id=portfolio.id,
            symbol="RELIANCE",
            entry_price=2465.0,
            shares=40,
            capital_used=98600.0,
            exit_price=2650.0,
            realised_pnl=7400.0,
            realised_pnl_pct=7.5,
            status=TradeStatus.CLOSED,
            exit_reason=TradeExitReason.TARGET1,
        )
        test_db_session.add(trade)
        test_db_session.commit()
        
        assert trade.realised_pnl == 7400.0
        assert trade.realised_pnl_pct == 7.5
        assert trade.exit_reason == TradeExitReason.TARGET1
    
    def test_paper_trade_closed_with_loss(self, mock_portfolio_factory, test_db_session):
        """Test closed trade with loss calculation."""
        portfolio = mock_portfolio_factory()
        
        trade = PaperTrade(
            portfolio_id=portfolio.id,
            symbol="TCS",
            entry_price=3500.0,
            shares=20,
            capital_used=70000.0,
            exit_price=3400.0,
            realised_pnl=-2000.0,
            realised_pnl_pct=-2.86,
            status=TradeStatus.CLOSED,
            exit_reason=TradeExitReason.STOP,
        )
        test_db_session.add(trade)
        test_db_session.commit()
        
        assert trade.realised_pnl == -2000.0
        assert trade.exit_reason == TradeExitReason.STOP
    
    def test_trade_exit_reason_enum(self, mock_portfolio_factory, test_db_session):
        """Test all TradeExitReason enum values."""
        portfolio = mock_portfolio_factory()
        
        exit_reasons = [
            TradeExitReason.TARGET1,
            TradeExitReason.TARGET2,
            TradeExitReason.STOP,
            TradeExitReason.MANUAL,
            TradeExitReason.SIGNAL,
            TradeExitReason.EXPIRED,
        ]
        
        for reason in exit_reasons:
            trade = PaperTrade(
                portfolio_id=portfolio.id,
                symbol=f"TEST_{reason.value}",
                entry_price=100.0,
                shares=10,
                capital_used=1000.0,
                exit_price=105.0,
                status=TradeStatus.CLOSED,
                exit_reason=reason,
            )
            test_db_session.add(trade)
        
        test_db_session.commit()
        
        saved_trades = test_db_session.query(PaperTrade).all()
        assert len(saved_trades) == 6


class TestWatchlistModel:
    """Test Watchlist model."""
    
    def test_create_watchlist_entry(self, test_db_session):
        """Test creating a Watchlist entry."""
        watchlist = Watchlist(
            symbol="INFY",
            exchange="NSE",
            notes="High potential breakout candidate",
        )
        test_db_session.add(watchlist)
        test_db_session.commit()
        
        assert watchlist.id is not None
        assert watchlist.symbol == "INFY"
    
    def test_watchlist_unique_symbol_constraint(self, test_db_session):
        """Test that symbol must be unique in watchlist."""
        w1 = Watchlist(symbol="INFY", exchange="NSE")
        test_db_session.add(w1)
        test_db_session.commit()
        
        w2 = Watchlist(symbol="INFY", exchange="NSE")
        test_db_session.add(w2)
        
        with pytest.raises(Exception):  # IntegrityError
            test_db_session.commit()


class TestNewsEventModel:
    """Test NewsEvent model."""
    
    def test_create_news_event(self, test_db_session):
        """Test creating a NewsEvent instance."""
        news = NewsEvent(
            symbol="RELIANCE",
            headline="Company announces Q4 results",
            source="Economic Times",
            published_at=datetime.utcnow(),
            sentiment="positive",
            is_material=True,
            alert_sent=False,
        )
        test_db_session.add(news)
        test_db_session.commit()
        
        assert news.id is not None
        assert news.symbol == "RELIANCE"
        assert news.is_material is True
    
    def test_news_event_sentiment_values(self, test_db_session):
        """Test different sentiment values."""
        sentiments = ["positive", "negative", "neutral"]
        
        for sentiment in sentiments:
            news = NewsEvent(
                symbol=f"TEST_{sentiment}",
                headline=f"Test {sentiment} news",
                sentiment=sentiment,
            )
            test_db_session.add(news)
        
        test_db_session.commit()
        
        saved_news = test_db_session.query(NewsEvent).all()
        assert len(saved_news) == 3


class TestRejectedHeadlineModel:
    """Test RejectedHeadline model."""
    
    def test_create_rejected_headline(self, test_db_session):
        """Test creating a RejectedHeadline instance."""
        rejected = RejectedHeadline(
            symbol="RELIANCE",
            headline="Generic market news",
            source="NewsAPI",
            published_at=datetime.utcnow(),
            filter_status="no_keyword",
        )
        test_db_session.add(rejected)
        test_db_session.commit()
        
        assert rejected.id is not None
        assert rejected.filter_status == "no_keyword"
    
    def test_rejected_headline_filter_statuses(self, test_db_session):
        """Test different filter status values."""
        statuses = ["stoplist", "no_keyword"]
        
        for status in statuses:
            rejected = RejectedHeadline(
                symbol="TEST",
                headline=f"Test {status}",
                filter_status=status,
            )
            test_db_session.add(rejected)
        
        test_db_session.commit()
        
        saved = test_db_session.query(RejectedHeadline).all()
        assert len(saved) == 2


class TestBacktestResultModel:
    """Test BacktestResult model."""
    
    def test_create_backtest_result(self, test_db_session):
        """Test creating a BacktestResult instance."""
        result = BacktestResult(
            symbol="RELIANCE",
            bundle_name="trend",
            run_date=date(2026, 5, 25),
            win_rate=0.65,
            avg_return_pct=3.5,
            max_drawdown_pct=-8.2,
            sharpe_ratio=1.8,
            total_trades=15,
            weight_assigned=0.4,
        )
        test_db_session.add(result)
        test_db_session.commit()
        
        assert result.id is not None
        assert result.bundle_name == "trend"
        assert result.sharpe_ratio == 1.8
    
    def test_backtest_result_all_bundles(self, test_db_session):
        """Test creating results for all bundle types."""
        bundles = ["trend", "reversal", "breakout", "smc", "composite"]
        run_date = date(2026, 5, 25)
        
        for bundle in bundles:
            result = BacktestResult(
                symbol="RELIANCE",
                bundle_name=bundle,
                run_date=run_date,
                win_rate=0.6,
                sharpe_ratio=1.5,
                total_trades=10,
            )
            test_db_session.add(result)
        
        test_db_session.commit()
        
        saved_results = test_db_session.query(BacktestResult).all()
        assert len(saved_results) == 5


class TestDatabaseSession:
    """Test database session management."""
    
    def test_session_rollback(self, test_db_session):
        """Test that session rollback works correctly."""
        rec = Recommendation(
            symbol="TEST",
            recommendation=RecommendationVerdict.BUY,
            entry_low=100.0,
            entry_high=110.0,
            entry_mid=Decimal("105.00"),
        )
        test_db_session.add(rec)
        test_db_session.rollback()
        
        # Should not be in database
        count = test_db_session.query(Recommendation).count()
        assert count == 0
    
    def test_session_isolation(self, test_db_session):
        """Test that each test gets a clean session."""
        # This test should start with empty database
        count = test_db_session.query(Recommendation).count()
        assert count == 0
