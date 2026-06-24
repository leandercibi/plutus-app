# tests/test_tickertape/test_tickertape.py
"""
Unit tests for tickertape.py — 100% offline: no network calls.

Tests cover:
  - Cache read/write/expiry
  - SECTOR_FALLBACK path
  - Live API fallback with monkeypatched HTTP
  - Beta computation (API path + offline OHLCV path)
  - MF holdings delta parsing
  - Cache invalidation
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "-1")

from plutus.data.tickertape import (
    SECTOR_FALLBACK,
    _cache_path,
    _parse_mf_holdings,
    _read_cache,
    _write_cache,
    get_beta,
    get_mf_holdings_delta,
    get_sector,
    invalidate_cache,
)


# ── Cache helpers ──────────────────────────────────────────────────────────────


class TestCacheHelpers:
    def test_write_and_read_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        _write_cache("TCS", "sector", {"sector": "IT", "source": "test"})
        result = _read_cache("TCS", "sector")
        assert result == {"sector": "IT", "source": "test"}

    def test_read_nonexistent_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        assert _read_cache("RELIANCE", "sector") is None

    def test_expired_cache_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        # TTL set to -1 so any file (age >= 0) is immediately considered expired
        monkeypatch.setattr("plutus.data.tickertape.CACHE_TTL_HOURS", -1)
        _write_cache("TCS", "beta", {"beta": 0.9, "source": "test"})
        assert _read_cache("TCS", "beta") is None

    def test_fresh_cache_returns_data(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        _write_cache(
            "INFY",
            "mf_delta",
            {"verdict": "ACCUMULATING", "change_pct": 5.0, "mf_count": 12},
        )
        result = _read_cache("INFY", "mf_delta")
        assert result["verdict"] == "ACCUMULATING"

    def test_corrupted_cache_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        p = _cache_path("WIPRO", "sector")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("NOT_VALID_JSON")
        assert _read_cache("WIPRO", "sector") is None

    def test_cache_path_normalizes_to_uppercase(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        _write_cache("tcs", "sector", {"sector": "IT"})
        # Should be readable with uppercase
        assert _read_cache("TCS", "sector") is not None


# ── SECTOR_FALLBACK ────────────────────────────────────────────────────────────


class TestSectorFallback:
    def test_fallback_covers_major_stocks(self):
        for sym in ("RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"):
            assert sym in SECTOR_FALLBACK, f"{sym} missing from SECTOR_FALLBACK"

    def test_fallback_returns_non_empty_string(self):
        for sym, sector in SECTOR_FALLBACK.items():
            assert isinstance(sector, str) and len(sector) > 0, f"{sym}: empty sector"

    def test_get_sector_uses_fallback_before_api(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        # Patch _get to raise so we can confirm it's never called
        with patch("plutus.data.tickertape._get") as mock_get:
            sector = get_sector("RELIANCE")
        assert sector == "ENERGY"
        mock_get.assert_not_called()

    def test_get_sector_caches_fallback_result(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        with patch("plutus.data.tickertape._get"):
            get_sector("TCS")
        cached = _read_cache("TCS", "sector")
        assert cached == {"sector": "IT", "source": "fallback"}


# ── get_sector live API path ───────────────────────────────────────────────────


class TestGetSectorAPI:
    def test_uses_disk_cache_when_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        _write_cache("NEWCO", "sector", {"sector": "FINTECH", "source": "api"})
        with patch("plutus.data.tickertape._get") as mock_get:
            sector = get_sector("NEWCO")
        assert sector == "FINTECH"
        mock_get.assert_not_called()

    def test_api_response_sector_field(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        with patch("plutus.data.tickertape._get", return_value={"sector": "MEDIA"}):
            sector = get_sector("ZEEL")
        assert sector == "MEDIA"

    def test_api_response_nested_data_field(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        with patch(
            "plutus.data.tickertape._get", return_value={"data": {"sector": "REALTY"}}
        ):
            sector = get_sector("NEWCO2")
        assert sector == "REALTY"

    def test_api_down_returns_none_for_unknown_symbol(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        with patch("plutus.data.tickertape._get", return_value=None):
            sector = get_sector("UNKNOWNSYM999")
        assert sector is None


# ── get_beta ───────────────────────────────────────────────────────────────────


class TestGetBeta:
    def test_uses_disk_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        _write_cache("HDFCBANK", "beta", {"beta": 1.2, "source": "api"})
        with patch("plutus.data.tickertape._get") as mock_get:
            beta = get_beta("HDFCBANK")
        assert beta == pytest.approx(1.2)
        mock_get.assert_not_called()

    def test_api_beta_field(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        with patch("plutus.data.tickertape._get", return_value={"beta": 0.85}):
            beta = get_beta("ICICIBANK")
        assert beta == pytest.approx(0.85)

    def test_api_nested_beta_field(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        with patch(
            "plutus.data.tickertape._get", return_value={"data": {"beta": 1.35}}
        ):
            beta = get_beta("KOTAKBANK")
        assert beta == pytest.approx(1.35)

    def test_api_down_falls_back_to_local_compute(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        with patch("plutus.data.tickertape._get", return_value=None):
            with patch(
                "plutus.data.tickertape._compute_beta_locally", return_value=0.75
            ) as mock_local:
                beta = get_beta("AXISBANK")
        assert beta == pytest.approx(0.75)
        mock_local.assert_called_once_with("AXISBANK")

    def test_full_api_failure_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        with patch("plutus.data.tickertape._get", return_value=None):
            with patch(
                "plutus.data.tickertape._compute_beta_locally", return_value=None
            ):
                beta = get_beta("UNKNOWNSYM999")
        assert beta is None


# ── _parse_mf_holdings ─────────────────────────────────────────────────────────


class TestParseMfHoldings:
    def test_accumulating_verdict(self):
        raw = {
            "data": [
                {"type": "mutual fund", "currentHolding": 110, "previousHolding": 100},
                {"type": "mutual fund", "currentHolding": 105, "previousHolding": 100},
            ]
        }
        result = _parse_mf_holdings(raw)
        assert result["verdict"] == "ACCUMULATING"
        assert result["change_pct"] > 2.0
        assert result["mf_count"] == 2

    def test_reducing_verdict(self):
        raw = {
            "data": [
                {"type": "mutual fund", "currentHolding": 90, "previousHolding": 100},
                {"type": "mutual fund", "currentHolding": 92, "previousHolding": 100},
            ]
        }
        result = _parse_mf_holdings(raw)
        assert result["verdict"] == "REDUCING"
        assert result["change_pct"] < -2.0

    def test_neutral_verdict(self):
        raw = {
            "data": [
                {"type": "mutual fund", "currentHolding": 101, "previousHolding": 100},
            ]
        }
        result = _parse_mf_holdings(raw)
        assert result["verdict"] == "NEUTRAL"

    def test_dict_with_mutualfund_key(self):
        raw = {
            "mutualFund": [
                {"current": 120, "previous": 100},
                {"current": 115, "previous": 100},
            ]
        }
        result = _parse_mf_holdings(raw)
        assert result["verdict"] == "ACCUMULATING"
        assert result["mf_count"] == 2

    def test_missing_previous_skips_entry(self):
        raw = {
            "data": [
                {"type": "mutual fund", "currentHolding": 110},  # no previousHolding
            ]
        }
        result = _parse_mf_holdings(raw)
        # No changes computed → falls back to UNKNOWN
        assert result["verdict"] == "UNKNOWN"

    def test_zero_previous_skips_division(self):
        raw = {
            "data": [
                {"type": "mutual fund", "currentHolding": 50, "previousHolding": 0},
            ]
        }
        result = _parse_mf_holdings(raw)
        assert result["verdict"] == "UNKNOWN"

    def test_empty_data_returns_unknown(self):
        assert _parse_mf_holdings({})["verdict"] == "UNKNOWN"
        assert _parse_mf_holdings({"data": []})["verdict"] == "UNKNOWN"

    def test_non_mf_entries_filtered_out(self):
        raw = {
            "data": [
                {"type": "FII", "currentHolding": 200, "previousHolding": 100},
                {"type": "mutual fund", "currentHolding": 105, "previousHolding": 100},
            ]
        }
        result = _parse_mf_holdings(raw)
        # Only 1 MF entry
        assert result["mf_count"] == 1


# ── get_mf_holdings_delta ──────────────────────────────────────────────────────


class TestGetMfHoldingsDelta:
    def test_uses_disk_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        cached = {"verdict": "ACCUMULATING", "change_pct": 7.5, "mf_count": 30}
        _write_cache("TCS", "mf_delta", cached)
        with patch("plutus.data.tickertape._get") as mock_get:
            result = get_mf_holdings_delta("TCS")
        assert result["verdict"] == "ACCUMULATING"
        mock_get.assert_not_called()

    def test_api_response_parsed(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        api_response = {
            "data": [
                {"type": "mutual fund", "currentHolding": 110, "previousHolding": 100},
            ]
        }
        with patch("plutus.data.tickertape._get", return_value=api_response):
            result = get_mf_holdings_delta("INFY")
        assert result["verdict"] == "ACCUMULATING"

    def test_api_down_returns_unknown(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        with patch("plutus.data.tickertape._get", return_value=None):
            result = get_mf_holdings_delta("UNKNOWNSYM999")
        assert result["verdict"] == "UNKNOWN"
        assert result["change_pct"] is None
        assert result["mf_count"] == 0


# ── invalidate_cache ───────────────────────────────────────────────────────────


class TestInvalidateCache:
    def test_removes_all_dtype_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        for dtype in ("sector", "beta", "mf_delta"):
            _write_cache("RELIANCE", dtype, {"x": 1})
        invalidate_cache("RELIANCE")
        for dtype in ("sector", "beta", "mf_delta"):
            assert _read_cache("RELIANCE", dtype) is None

    def test_no_error_when_nothing_cached(self, tmp_path, monkeypatch):
        monkeypatch.setattr("plutus.data.tickertape.CACHE_DIR", tmp_path)
        invalidate_cache("NOSUCHSYM")  # Should not raise
