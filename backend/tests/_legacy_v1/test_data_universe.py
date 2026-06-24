"""Tests for plutus.data.universe module."""

import pytest
import json
from pathlib import Path
from datetime import date
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from plutus.data import universe


class TestLoadSeedSymbols:
    def test_load_valid_csv(self, tmp_path, monkeypatch):
        csv_path = tmp_path / "seed.csv"
        csv_path.write_text("symbol\nRELIANCE\nTCS\nINFY\n")
        monkeypatch.setattr(
            "plutus.data.universe.settings.UNIVERSE_SEED_CSV", str(csv_path)
        )

        symbols = universe._load_seed_symbols()
        assert symbols == ["RELIANCE", "TCS", "INFY"]

    def test_deduplication(self, tmp_path, monkeypatch):
        csv_path = tmp_path / "seed.csv"
        csv_path.write_text("symbol\nRELIANCE\nTCS\nRELIANCE\nINFY\n")
        monkeypatch.setattr(
            "plutus.data.universe.settings.UNIVERSE_SEED_CSV", str(csv_path)
        )

        symbols = universe._load_seed_symbols()
        assert symbols == ["RELIANCE", "TCS", "INFY"]

    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.universe.settings.UNIVERSE_SEED_CSV",
            str(tmp_path / "missing.csv"),
        )

        with pytest.raises(FileNotFoundError):
            universe._load_seed_symbols()


class TestLoadFnoBanList:
    @patch("plutus.data.universe.requests.get")
    def test_fetch_from_api(self, mock_get, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.universe.FNO_BAN_FILE", tmp_path / "ban.txt")

        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [{"symbol": "BANNED1"}, {"symbol": "BANNED2"}]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        banned = universe._load_fno_ban_list()
        assert banned == {"BANNED1", "BANNED2"}
        assert (tmp_path / "ban.txt").exists()

    def test_use_stale_file_on_api_failure(self, tmp_path, monkeypatch):
        ban_file = tmp_path / "ban.txt"
        ban_file.write_text("STALE1\nSTALE2\n")
        monkeypatch.setattr("plutus.data.universe.FNO_BAN_FILE", ban_file)

        with patch(
            "plutus.data.universe.requests.get", side_effect=Exception("API down")
        ):
            banned = universe._load_fno_ban_list()
            assert banned == {"STALE1", "STALE2"}

    def test_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.universe.FNO_BAN_FILE", tmp_path / "missing.txt"
        )

        with patch(
            "plutus.data.universe.requests.get", side_effect=Exception("API down")
        ):
            banned = universe._load_fno_ban_list()
            assert banned == set()


class TestCaching:
    def test_week_tag_format(self):
        tag = universe._week_tag(date(2026, 5, 31))
        assert tag.startswith("2026W")

    def test_cache_save_and_load(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir()
        monkeypatch.setattr("plutus.data.universe.CACHE_DIR", cache_dir)

        symbols = ["RELIANCE", "TCS", "INFY"]
        universe._save_cached_universe(symbols)

        loaded = universe._load_cached_universe()
        assert loaded == symbols

    def test_cache_miss_returns_none(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir()
        monkeypatch.setattr("plutus.data.universe.CACHE_DIR", cache_dir)

        loaded = universe._load_cached_universe()
        assert loaded is None


class TestGetUniverse:
    @patch("plutus.data.universe._load_cached_universe")
    def test_returns_cached_when_available(self, mock_cache):
        mock_cache.return_value = ["CACHED1", "CACHED2"]

        result = universe.get_universe(use_cache=True)
        assert result == ["CACHED1", "CACHED2"]

    @patch("plutus.data.universe._load_cached_universe")
    @patch("plutus.data.universe._load_seed_symbols")
    @patch("plutus.data.universe._load_fno_ban_list")
    @patch("plutus.data.universe.fetch_ohlcv")
    @patch("plutus.data.universe._save_cached_universe")
    def test_filters_banned_symbols(
        self, mock_save, mock_fetch, mock_ban, mock_seed, mock_cache, monkeypatch
    ):
        mock_cache.return_value = None
        mock_seed.return_value = ["RELIANCE", "BANNED1", "TCS"]
        mock_ban.return_value = {"BANNED1"}

        df = pd.DataFrame(
            {
                "Close": [2500.0] * 90,
                "Volume": [1000000] * 90,
            },
            index=pd.date_range(end="2026-05-31", periods=90),
        )
        mock_fetch.return_value = df

        monkeypatch.setattr("plutus.data.universe.settings.UNIVERSE_PRICE_MIN", 50.0)
        monkeypatch.setattr("plutus.data.universe.settings.UNIVERSE_PRICE_MAX", 5000.0)
        monkeypatch.setattr(
            "plutus.data.universe.settings.UNIVERSE_MIN_AVG_VOLUME", 500000
        )
        monkeypatch.setattr(
            "plutus.data.universe.settings.UNIVERSE_MIN_AVG_VALUE_CR", 10.0
        )

        result = universe.get_universe(use_cache=False)
        assert "BANNED1" not in result
        assert "RELIANCE" in result or "TCS" in result

    @patch("plutus.data.universe._load_cached_universe")
    @patch("plutus.data.universe._load_seed_symbols")
    @patch("plutus.data.universe._load_fno_ban_list")
    @patch("plutus.data.universe.fetch_ohlcv")
    @patch("plutus.data.universe._save_cached_universe")
    def test_filters_by_price(
        self, mock_save, mock_fetch, mock_ban, mock_seed, mock_cache, monkeypatch
    ):
        mock_cache.return_value = None
        mock_seed.return_value = ["CHEAP", "EXPENSIVE"]
        mock_ban.return_value = set()

        def fetch_side_effect(symbol, **kwargs):
            price = 30.0 if symbol == "CHEAP" else 6000.0
            return pd.DataFrame(
                {
                    "Close": [price] * 90,
                    "Volume": [1000000] * 90,
                },
                index=pd.date_range(end="2026-05-31", periods=90),
            )

        mock_fetch.side_effect = fetch_side_effect

        monkeypatch.setattr("plutus.data.universe.settings.UNIVERSE_PRICE_MIN", 50.0)
        monkeypatch.setattr("plutus.data.universe.settings.UNIVERSE_PRICE_MAX", 5000.0)
        monkeypatch.setattr(
            "plutus.data.universe.settings.UNIVERSE_MIN_AVG_VOLUME", 500000
        )
        monkeypatch.setattr(
            "plutus.data.universe.settings.UNIVERSE_MIN_AVG_VALUE_CR", 10.0
        )

        result = universe.get_universe(use_cache=False)
        assert "CHEAP" not in result
        assert "EXPENSIVE" not in result

    @patch("plutus.data.universe._load_cached_universe")
    @patch("plutus.data.universe._load_seed_symbols")
    @patch("plutus.data.universe._load_fno_ban_list")
    @patch("plutus.data.universe.fetch_ohlcv")
    @patch("plutus.data.universe._save_cached_universe")
    def test_filters_by_volume(
        self, mock_save, mock_fetch, mock_ban, mock_seed, mock_cache, monkeypatch
    ):
        mock_cache.return_value = None
        mock_seed.return_value = ["LOWVOL"]
        mock_ban.return_value = set()

        df = pd.DataFrame(
            {
                "Close": [2500.0] * 90,
                "Volume": [100000] * 90,  # Below minimum
            },
            index=pd.date_range(end="2026-05-31", periods=90),
        )
        mock_fetch.return_value = df

        monkeypatch.setattr("plutus.data.universe.settings.UNIVERSE_PRICE_MIN", 50.0)
        monkeypatch.setattr("plutus.data.universe.settings.UNIVERSE_PRICE_MAX", 5000.0)
        monkeypatch.setattr(
            "plutus.data.universe.settings.UNIVERSE_MIN_AVG_VOLUME", 500000
        )
        monkeypatch.setattr(
            "plutus.data.universe.settings.UNIVERSE_MIN_AVG_VALUE_CR", 10.0
        )

        result = universe.get_universe(use_cache=False)
        assert "LOWVOL" not in result


class TestWatchlistIntegration:
    @patch("plutus.db.session.SessionLocal")
    def test_get_watchlist_symbols(self, mock_session_local):
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        mock_watchlist = [
            Mock(symbol="WATCH1"),
            Mock(symbol="WATCH2"),
        ]
        mock_session.query.return_value.all.return_value = mock_watchlist

        result = universe.get_watchlist_symbols()
        assert result == ["WATCH1", "WATCH2"]

    @patch("plutus.data.universe.get_universe")
    @patch("plutus.data.universe.get_watchlist_symbols")
    def test_get_full_analysis_set(self, mock_watchlist, mock_universe):
        mock_universe.return_value = ["RELIANCE", "TCS"]
        mock_watchlist.return_value = ["WATCH1", "RELIANCE"]

        result = universe.get_full_analysis_set()
        assert set(result) == {"RELIANCE", "TCS", "WATCH1"}
        assert result.index("RELIANCE") < result.index("WATCH1")  # Universe first
