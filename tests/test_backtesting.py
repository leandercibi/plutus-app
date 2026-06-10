"""Tests for backtesting runner and paper trader."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, date

from plutus.backtesting.runner import (
    run_bundle,
    run_all_bundles,
    select_best_bundles,
    weekly_pipeline,
    save_backtest_results,
    BundleResult,
    BUNDLE_MAP,
)
from plutus.backtesting.paper_trader import PaperTrader, BuyResult


class TestRunBundle:
    """Test single bundle execution."""
    
    @patch('plutus.backtesting.runner.fetch_ohlcv')
    def test_run_bundle_success(self, mock_fetch, sample_ohlcv_uptrend):
        """Test successful bundle execution."""
        mock_fetch.return_value = sample_ohlcv_uptrend
        
        result = run_bundle("RELIANCE", "trend", days=90)
        
        assert isinstance(result, BundleResult)
        assert result.bundle_name == "trend"
        assert 0.0 <= result.win_rate <= 1.0
        assert isinstance(result.avg_return_pct, float)
        assert isinstance(result.sharpe_ratio, float)
        assert result.total_trades >= 0
        assert isinstance(result.trades, list)
    
    @patch('plutus.backtesting.runner.fetch_ohlcv')
    def test_run_bundle_insufficient_data(self, mock_fetch, sample_ohlcv_insufficient):
        """Insufficient data raises InsufficientDataError (not silently swallowed)."""
        mock_fetch.return_value = sample_ohlcv_insufficient
        from plutus.data.ohlcv import InsufficientDataError
        with pytest.raises(InsufficientDataError):
            run_bundle("RELIANCE", "trend", days=90)

    @patch('plutus.backtesting.runner.fetch_ohlcv')
    def test_run_bundle_no_data(self, mock_fetch):
        """None data raises InsufficientDataError (0 bars < MIN_BARS_REQUIRED)."""
        mock_fetch.return_value = None
        from plutus.data.ohlcv import InsufficientDataError
        with pytest.raises(InsufficientDataError):
            run_bundle("INVALID", "trend", days=90)
    
    @patch('plutus.backtesting.runner.fetch_ohlcv')
    def test_run_bundle_invalid_bundle_name(self, mock_fetch, sample_ohlcv_uptrend):
        """Test invalid bundle name raises ValueError."""
        mock_fetch.return_value = sample_ohlcv_uptrend
        
        with pytest.raises(ValueError, match="Unknown bundle"):
            run_bundle("RELIANCE", "invalid_bundle", days=90)
    
    @patch('plutus.backtesting.runner.fetch_ohlcv')
    def test_run_bundle_all_bundle_types(self, mock_fetch, sample_ohlcv_uptrend):
        """Test all 5 bundle types execute successfully."""
        mock_fetch.return_value = sample_ohlcv_uptrend
        
        for bundle_name in BUNDLE_MAP.keys():
            result = run_bundle("RELIANCE", bundle_name, days=90)
            assert result.bundle_name == bundle_name
            assert isinstance(result, BundleResult)
    
    @patch('plutus.backtesting.runner.fetch_ohlcv')
    def test_run_bundle_result_metrics(self, mock_fetch, sample_ohlcv_uptrend):
        """Test result metrics are properly calculated."""
        mock_fetch.return_value = sample_ohlcv_uptrend
        
        result = run_bundle("RELIANCE", "trend", days=90)
        
        # Win rate should be between 0 and 1
        assert 0.0 <= result.win_rate <= 1.0
        
        # If trades exist, check trade structure
        if result.total_trades > 0:
            assert len(result.trades) == result.total_trades
            for trade in result.trades:
                assert "pnl" in trade
                assert "pnl_pct" in trade
                assert "entry" in trade
                assert "exit" in trade


class TestRunAllBundles:
    """Test batch execution of all bundles."""
    
    @patch('plutus.backtesting.runner.fetch_ohlcv')
    def test_run_all_bundles_returns_five(self, mock_fetch, sample_ohlcv_uptrend):
        """Test run_all_bundles returns exactly 5 results."""
        mock_fetch.return_value = sample_ohlcv_uptrend
        
        results = run_all_bundles("RELIANCE", days=90)

        assert len(results) == len(BUNDLE_MAP)
        assert set(results.keys()) == set(BUNDLE_MAP.keys())
        
        for bundle_name, result in results.items():
            assert isinstance(result, BundleResult)
            assert result.bundle_name == bundle_name
    
    @patch('plutus.backtesting.runner.fetch_ohlcv')
    def test_run_all_bundles_with_no_data(self, mock_fetch):
        """run_all_bundles with no data propagates InsufficientDataError."""
        mock_fetch.return_value = None
        from plutus.data.ohlcv import InsufficientDataError
        with pytest.raises(InsufficientDataError):
            run_all_bundles("INVALID", days=90)


class TestSelectBestBundles:
    """Test top 2 bundle selection logic."""
    
    def test_select_best_bundles_by_sharpe(self):
        """Test selection picks top 2 by Sharpe ratio."""
        results = {
            "trend": BundleResult("trend", 0.6, 2.5, 10.0, 1.5, 10, []),
            "reversal": BundleResult("reversal", 0.5, 1.8, 8.0, 0.8, 8, []),
            "breakout": BundleResult("breakout", 0.7, 3.2, 12.0, 2.1, 12, []),
            "smc": BundleResult("smc", 0.55, 2.0, 9.0, 1.2, 9, []),
            "composite": BundleResult("composite", 0.65, 2.8, 11.0, 1.8, 11, []),
        }
        
        best = select_best_bundles(results)
        
        assert len(best) == 2
        assert best[0] == "breakout"  # Highest Sharpe: 2.1
        assert best[1] == "composite"  # Second highest: 1.8
    
    def test_select_best_bundles_demotes_zero_trades(self):
        """Test bundles with 0 trades are demoted."""
        results = {
            "trend": BundleResult("trend", 0.0, 0.0, 0.0, 3.0, 0, []),  # High Sharpe but 0 trades
            "reversal": BundleResult("reversal", 0.5, 1.8, 8.0, 0.8, 8, []),
            "breakout": BundleResult("breakout", 0.7, 3.2, 12.0, 1.2, 12, []),
            "smc": BundleResult("smc", 0.0, 0.0, 0.0, 2.5, 0, []),  # High Sharpe but 0 trades
            "composite": BundleResult("composite", 0.65, 2.8, 11.0, 0.9, 11, []),
        }
        
        best = select_best_bundles(results)
        
        assert len(best) == 2
        # Should pick breakout and composite, not trend/smc despite higher Sharpe
        assert "trend" not in best
        assert "smc" not in best
        assert "breakout" in best
        assert "composite" in best
    
    def test_select_best_bundles_all_zero_trades(self):
        """Test when all bundles have 0 trades."""
        results = {
            "trend": BundleResult("trend", 0.0, 0.0, 0.0, 0.0, 0, []),
            "reversal": BundleResult("reversal", 0.0, 0.0, 0.0, 0.0, 0, []),
            "breakout": BundleResult("breakout", 0.0, 0.0, 0.0, 0.0, 0, []),
            "smc": BundleResult("smc", 0.0, 0.0, 0.0, 0.0, 0, []),
            "composite": BundleResult("composite", 0.0, 0.0, 0.0, 0.0, 0, []),
        }
        
        best = select_best_bundles(results)
        
        # Should still return 2, but they're all equally bad
        assert len(best) == 2


class TestWeeklyPipeline:
    """Test weekly pipeline ranking."""
    
    @patch('plutus.backtesting.runner.save_backtest_results')
    @patch('plutus.backtesting.runner.run_all_bundles')
    @patch('plutus.backtesting.runner.get_universe')
    def test_weekly_pipeline_returns_top_20(self, mock_universe, mock_run_all, mock_save):
        """Test weekly pipeline returns top 20 symbols."""
        # Mock 30 symbols
        mock_universe.return_value = [f"SYM{i}" for i in range(30)]
        
        # Mock results with varying Sharpe ratios
        def mock_results(symbol, days):
            idx = int(symbol[3:])  # Extract number from SYM0, SYM1, etc.
            sharpe = 2.0 - (idx * 0.05)  # Decreasing Sharpe
            return {
                "trend": BundleResult("trend", 0.6, 2.0, 10.0, sharpe, 10, []),
                "reversal": BundleResult("reversal", 0.5, 1.5, 8.0, sharpe - 0.2, 8, []),
                "breakout": BundleResult("breakout", 0.7, 2.5, 12.0, sharpe - 0.1, 12, []),
                "smc": BundleResult("smc", 0.55, 1.8, 9.0, sharpe - 0.3, 9, []),
                "composite": BundleResult("composite", 0.65, 2.2, 11.0, sharpe - 0.15, 11, []),
            }
        
        mock_run_all.side_effect = mock_results
        
        top_symbols = weekly_pipeline(weekly_run_id=1, days=90)
        
        assert len(top_symbols) == 20
        # Should be sorted by best Sharpe (SYM0 has highest)
        assert top_symbols[0] == "SYM0"
        assert top_symbols[-1] == "SYM19"
    
    @patch('plutus.backtesting.runner.save_backtest_results')
    @patch('plutus.backtesting.runner.run_all_bundles')
    @patch('plutus.backtesting.runner.get_universe')
    def test_weekly_pipeline_filters_negative_sharpe(self, mock_universe, mock_run_all, mock_save):
        """Test weekly pipeline excludes symbols with no valid trades."""
        mock_universe.return_value = ["SYM1", "SYM2", "SYM3"]
        
        def mock_results(symbol, days):
            if symbol == "SYM1":
                # Good results
                return {
                    "trend": BundleResult("trend", 0.6, 2.0, 10.0, 1.5, 10, []),
                    "reversal": BundleResult("reversal", 0.5, 1.5, 8.0, 1.2, 8, []),
                    "breakout": BundleResult("breakout", 0.7, 2.5, 12.0, 1.8, 12, []),
                    "smc": BundleResult("smc", 0.55, 1.8, 9.0, 1.3, 9, []),
                    "composite": BundleResult("composite", 0.65, 2.2, 11.0, 1.6, 11, []),
                }
            else:
                # All bundles have 0 trades
                return {
                    "trend": BundleResult("trend", 0.0, 0.0, 0.0, 0.0, 0, []),
                    "reversal": BundleResult("reversal", 0.0, 0.0, 0.0, 0.0, 0, []),
                    "breakout": BundleResult("breakout", 0.0, 0.0, 0.0, 0.0, 0, []),
                    "smc": BundleResult("smc", 0.0, 0.0, 0.0, 0.0, 0, []),
                    "composite": BundleResult("composite", 0.0, 0.0, 0.0, 0.0, 0, []),
                }
        
        mock_run_all.side_effect = mock_results
        
        top_symbols = weekly_pipeline(weekly_run_id=1, days=90)
        
        # Should only return SYM1
        assert len(top_symbols) == 1
        assert top_symbols[0] == "SYM1"


class TestSaveBacktestResults:
    """Test backtest result persistence."""
    
    @patch('plutus.backtesting.runner.SessionLocal')
    @patch('plutus.backtesting.runner.BacktestResult')
    def test_save_backtest_results(self, mock_backtest_result, mock_session_local):
        """Test saving backtest results to database."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        
        results = {
            "trend": BundleResult("trend", 0.6, 2.5, 10.0, 1.5, 10, []),
            "reversal": BundleResult("reversal", 0.5, 1.8, 8.0, 0.8, 8, []),
        }
        
        save_backtest_results(weekly_run_id=1, symbol="RELIANCE", results=results)
        
        # Should call BacktestResult constructor 2 times (one per bundle)
        assert mock_backtest_result.call_count == 2
        assert mock_db.add.call_count == 2
        assert mock_db.commit.call_count == 1


class TestPaperTrader:
    """Test paper trading functionality."""
    
    @patch('plutus.backtesting.paper_trader.SessionLocal')
    def test_paper_trader_buy_success(self, mock_session_local):
        """Test successful paper trade buy."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        
        # Mock portfolio
        mock_portfolio = Mock()
        mock_portfolio.id = 1
        mock_portfolio.name = "test_portfolio"
        mock_portfolio.current_cash = 100_000.0
        mock_portfolio.initial_capital = 100_000.0
        mock_db.query.return_value.filter.return_value.first.return_value = mock_portfolio
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        
        # Mock trade
        mock_trade = Mock()
        mock_trade.id = 1
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None
        
        trader = PaperTrader("test_portfolio")
        result = trader.buy(symbol="RELIANCE", price=2500.0, shares=10, strategy_used="trend")
        
        assert isinstance(result, BuyResult)
        assert result.capital_used == 25_000.0
        assert mock_db.add.called
        assert mock_db.commit.called
    
    @patch('plutus.backtesting.paper_trader.SessionLocal')
    def test_paper_trader_buy_insufficient_cash(self, mock_session_local):
        """Test buy with insufficient cash raises ValueError."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        
        mock_portfolio = Mock()
        mock_portfolio.id = 1
        mock_portfolio.name = "test_portfolio"
        mock_portfolio.current_cash = 10_000.0
        mock_portfolio.initial_capital = 100_000.0
        mock_db.query.return_value.filter.return_value.first.return_value = mock_portfolio
        
        trader = PaperTrader("test_portfolio")
        
        with pytest.raises(ValueError, match="Insufficient cash"):
            trader.buy(symbol="RELIANCE", price=2500.0, shares=100)
    
    @patch('plutus.backtesting.paper_trader.SessionLocal')
    def test_paper_trader_buy_invalid_inputs(self, mock_session_local):
        """Test buy with invalid inputs raises ValueError."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        
        mock_portfolio = Mock()
        mock_portfolio.id = 1
        mock_portfolio.current_cash = 100_000.0
        mock_db.query.return_value.filter.return_value.first.return_value = mock_portfolio
        
        trader = PaperTrader("test_portfolio")
        
        with pytest.raises(ValueError, match="shares must be > 0"):
            trader.buy(symbol="RELIANCE", price=2500.0, shares=0)
        
        with pytest.raises(ValueError, match="price must be > 0"):
            trader.buy(symbol="RELIANCE", price=0, shares=10)
    
    @patch('plutus.backtesting.paper_trader.SessionLocal')
    def test_paper_trader_sell_success(self, mock_session_local):
        """Test successful paper trade sell."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        
        mock_portfolio = Mock()
        mock_portfolio.id = 1
        mock_portfolio.current_cash = 75_000.0
        mock_db.query.return_value.filter.return_value.first.return_value = mock_portfolio
        
        # Mock open trade
        mock_trade = Mock()
        mock_trade.id = 1
        mock_trade.symbol = "RELIANCE"
        mock_trade.entry_price = 2500.0
        mock_trade.shares = 10
        mock_trade.status = "OPEN"
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_trade
        
        trader = PaperTrader("test_portfolio")
        result = trader.sell(symbol="RELIANCE", price=2600.0, shares=10)
        
        assert result["shares_closed"] == 10
        assert result["realised_pnl"] == 1000.0  # (2600 - 2500) * 10
        assert result["realised_pnl_pct"] == 4.0  # 100/2500 * 100
        assert result["remaining_shares"] == 0
    
    @patch('plutus.backtesting.paper_trader.SessionLocal')
    def test_paper_trader_sell_no_position(self, mock_session_local):
        """Test sell with no open position raises ValueError."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        
        mock_portfolio = Mock()
        mock_portfolio.id = 1
        mock_portfolio.name = "test_portfolio"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_portfolio
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        
        trader = PaperTrader("test_portfolio")
        
        with pytest.raises(ValueError, match="No open position"):
            trader.sell(symbol="RELIANCE", price=2600.0, shares=10)
    
    @patch('plutus.backtesting.paper_trader.SessionLocal')
    def test_paper_trader_partial_sell(self, mock_session_local):
        """Test partial position close."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        
        mock_portfolio = Mock()
        mock_portfolio.id = 1
        mock_portfolio.current_cash = 75_000.0
        mock_db.query.return_value.filter.return_value.first.return_value = mock_portfolio
        
        # Mock open trade with 20 shares
        mock_trade = Mock()
        mock_trade.id = 1
        mock_trade.symbol = "RELIANCE"
        mock_trade.entry_price = 2500.0
        mock_trade.shares = 20
        mock_trade.capital_used = 50_000.0
        mock_trade.status = "OPEN"
        mock_trade.entry_date = datetime.now()
        mock_trade.direction = "LONG"
        mock_trade.strategy_used = "trend"
        mock_trade.linked_recommendation_id = None
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_trade
        
        trader = PaperTrader("test_portfolio")
        result = trader.sell(symbol="RELIANCE", price=2600.0, shares=10)
        
        assert result["shares_closed"] == 10
        assert result["remaining_shares"] == 10
        assert mock_db.add.called  # Should add closed sibling trade
