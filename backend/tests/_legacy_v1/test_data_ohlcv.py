"""Tests for plutus.data.ohlcv module."""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from plutus.data import ohlcv


class TestNseSymbol:
    def test_adds_ns_suffix(self):
        assert ohlcv._nse_symbol("RELIANCE", "NSE") == "RELIANCE.NS"

    def test_adds_bo_suffix(self):
        assert ohlcv._nse_symbol("RELIANCE", "BSE") == "RELIANCE.BO"

    def test_preserves_existing_suffix(self):
        assert ohlcv._nse_symbol("RELIANCE.NS", "NSE") == "RELIANCE.NS"
        assert ohlcv._nse_symbol("RELIANCE.BO", "BSE") == "RELIANCE.BO"


class TestCaching:
    def test_cache_path_format(self):
        path = ohlcv._cache_path("RELIANCE", 90)
        assert "RELIANCE" in str(path)
        assert "90" in str(path)
        assert path.suffix == ".parquet"

    def test_read_cache_miss(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.ohlcv.CACHE_DIR", tmp_path)
        result = ohlcv._read_cache("MISSING", 90)
        assert result is None

    def test_write_and_read_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.ohlcv.CACHE_DIR", tmp_path)

        df = pd.DataFrame(
            {
                "Open": [100, 101],
                "High": [102, 103],
                "Low": [98, 99],
                "Close": [101, 102],
                "Volume": [1000000, 1100000],
            },
            index=pd.date_range("2026-05-30", periods=2),
        )

        ohlcv._write_cache("TEST", 90, df)
        loaded = ohlcv._read_cache("TEST", 90)

        assert loaded is not None
        assert len(loaded) == 2
        assert list(loaded.columns) == ["Open", "High", "Low", "Close", "Volume"]

    def test_expired_cache_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.ohlcv.CACHE_DIR", tmp_path)
        monkeypatch.setattr("plutus.data.ohlcv.OHLCV_CACHE_TTL_HOURS", 0)

        df = pd.DataFrame(
            {
                "Open": [100],
                "High": [102],
                "Low": [98],
                "Close": [101],
                "Volume": [1000000],
            },
            index=pd.date_range("2026-05-30", periods=1),
        )

        ohlcv._write_cache("TEST", 90, df)

        # Sleep briefly to ensure cache is expired
        import time

        time.sleep(0.1)

        result = ohlcv._read_cache("TEST", 90)
        assert result is None


class TestFetchOhlcv:
    @patch("plutus.data.ohlcv.yf.download")
    def test_successful_fetch(self, mock_download):
        mock_df = pd.DataFrame(
            {
                "Open": [100.0] * 90,
                "High": [102.0] * 90,
                "Low": [98.0] * 90,
                "Close": [101.0] * 90,
                "Volume": [1000000] * 90,
            },
            index=pd.date_range(end="2026-05-31", periods=90),
        )
        mock_download.return_value = mock_df

        result = ohlcv.fetch_ohlcv("RELIANCE", days=90)

        assert len(result) == 90
        assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert result.index.tz is None  # Timezone-naive

    @patch("plutus.data.ohlcv.yf.download")
    def test_empty_data_raises_error(self, mock_download):
        mock_download.return_value = pd.DataFrame()

        with pytest.raises(ValueError, match="no data"):
            ohlcv.fetch_ohlcv("INVALID", days=90)

    @patch("plutus.data.ohlcv._read_cache")
    @patch("plutus.data.ohlcv.yf.download")
    def test_uses_cache_for_daily_interval(self, mock_download, mock_cache):
        cached_df = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [102.0],
                "Low": [98.0],
                "Close": [101.0],
                "Volume": [1000000],
            },
            index=pd.date_range("2026-05-31", periods=1),
        )
        mock_cache.return_value = cached_df

        result = ohlcv.fetch_ohlcv("RELIANCE", days=90, interval="1d")

        assert len(result) == 1
        mock_download.assert_not_called()

    @patch("plutus.data.ohlcv._read_cache")
    @patch("plutus.data.ohlcv.yf.download")
    def test_skips_cache_for_intraday(self, mock_download, mock_cache):
        mock_df = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [102.0],
                "Low": [98.0],
                "Close": [101.0],
                "Volume": [1000000],
            },
            index=pd.date_range("2026-05-31", periods=1),
        )
        mock_download.return_value = mock_df

        result = ohlcv.fetch_ohlcv("RELIANCE", days=1, interval="1h")

        mock_cache.assert_not_called()
        mock_download.assert_called_once()

    @patch("plutus.data.ohlcv.yf.download")
    def test_retry_on_failure(self, mock_download):
        mock_download.side_effect = [
            Exception("Network error"),
            Exception("Network error"),
            pd.DataFrame(
                {
                    "Open": [100.0],
                    "High": [102.0],
                    "Low": [98.0],
                    "Close": [101.0],
                    "Volume": [1000000],
                },
                index=pd.date_range("2026-05-31", periods=1),
            ),
        ]

        result = ohlcv.fetch_ohlcv("RELIANCE", days=1)
        assert len(result) == 1


class TestFetchLivePrice:
    @patch("plutus.data.ohlcv.yf.Ticker")
    def test_returns_last_price(self, mock_ticker):
        mock_info = Mock()
        mock_info.last_price = 2500.0
        mock_info.previous_close = 2480.0

        mock_ticker_instance = Mock()
        mock_ticker_instance.fast_info = mock_info
        mock_ticker.return_value = mock_ticker_instance

        price = ohlcv.fetch_live_price("RELIANCE")
        assert price == 2500.0

    @patch("plutus.data.ohlcv.yf.Ticker")
    def test_falls_back_to_previous_close(self, mock_ticker):
        mock_info = Mock()
        mock_info.last_price = None
        mock_info.previous_close = 2480.0

        mock_ticker_instance = Mock()
        mock_ticker_instance.fast_info = mock_info
        mock_ticker.return_value = mock_ticker_instance

        price = ohlcv.fetch_live_price("RELIANCE")
        assert price == 2480.0


class TestAddIndicators:
    def test_adds_indicators(self):
        df = pd.DataFrame(
            {
                "Open": [100 + i for i in range(60)],
                "High": [102 + i for i in range(60)],
                "Low": [98 + i for i in range(60)],
                "Close": [101 + i for i in range(60)],
                "Volume": [1000000 + i * 10000 for i in range(60)],
            },
            index=pd.date_range("2026-04-01", periods=60),
        )

        result = ohlcv.add_indicators(df)

        # Check that key indicators are added
        assert "EMA_9" in result.columns
        assert "RSI_14" in result.columns
        assert "MACD_12_26_9" in result.columns
        assert "BBL_20_2.0" in result.columns  # Bollinger lower
        assert "ATRr_14" in result.columns
        assert "Volume_MA20" in result.columns

        # Check that rows with NaN are dropped
        assert not result["EMA_9"].isna().any()
        assert not result["RSI_14"].isna().any()

    def test_handles_insufficient_data(self):
        df = pd.DataFrame(
            {
                "Open": [100, 101],
                "High": [102, 103],
                "Low": [98, 99],
                "Close": [101, 102],
                "Volume": [1000000, 1100000],
            },
            index=pd.date_range("2026-05-30", periods=2),
        )

        result = ohlcv.add_indicators(df)
        # Should return empty DataFrame after dropna (insufficient data for indicators)
        assert len(result) == 0
