# tests/test_phase7_portfolio_analyze.py
"""
Phase 7 acceptance tests: analyze card + portfolio tab.

All tests are 100% offline — no DB connections, no HTTP, no yfinance.

AppTest.from_function uses inspect.getsource — closures do NOT capture outer
scope. Outer-scope values must be passed via the `kwargs=` parameter of
AppTest.from_function so they are pickled separately and injected as arguments.
"""
from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ── Shared data factories ─────────────────────────────────────────────────────


def _make_analyze_response(rec: str = "BUY") -> dict:
    return {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "current_price": 2800.50,
        "recommendation": rec,
        "confidence": 7.5,
        "entry_zone": [2790.0, 2820.0],
        "targets": [2950.0, 3100.0],
        "stop_loss": 2720.0,
        "risk_reward": 2.5,
        "position": {
            "shares": 35,
            "capital": 98017.5,
            "pct_of_portfolio": 9.8,
            "max_loss_inr": 2817.5,
        },
        "hold_days": "5-8",
        "strategy": "Trend + VCP",
        "signals": {
            "technical": {"EMA_alignment": "bullish", "RSI_14": 62.3},
            "sentiment": {"score": 0.4, "label": "positive"},
            "smart_money": {"fii_bias": "BUY", "mf_delta": "accumulating"},
        },
        "risk_flags": ["F&O ban active", "Earnings in 12 days"],
        "reasoning": "Strong breakout from VCP consolidation above EMA50.",
        "analysis_time_sec": 1.23,
        "cache_hit": False,
    }


def _make_mock_portfolio():
    from plutus.db.models import MockPortfolio

    p = MockPortfolio()
    p.id = 1
    p.name = "test_port"
    p.initial_capital = Decimal("100000.00")
    p.notes = ""
    return p


def _app_path():
    return os.path.join(os.path.dirname(__file__), "..", "src", "dashboard.py")


# ── render_analyze_card unit tests ────────────────────────────────────────────

# Each _app function takes `data` as a kwarg (injected via AppTest kwargs=).
# Do NOT reference outer-scope names inside these functions — getsource means
# only the function body is serialized; closures do not cross the subprocess.


def _app_render_card(data):
    import sys, os

    sys.path.insert(0, os.path.abspath("src"))
    from plutus.dashboard.analyze_card import render_analyze_card

    render_analyze_card(data)


class TestAnalyzeCard:
    """Tests for render_analyze_card in plutus.dashboard.analyze_card."""

    @pytest.mark.parametrize("rec", ["BUY", "WATCH", "HOLD", "SELL", "AVOID"])
    def test_renders_all_recommendation_types(self, rec):
        from streamlit.testing.v1 import AppTest

        data = _make_analyze_response(rec)
        at = AppTest.from_function(
            _app_render_card, default_timeout=15, kwargs={"data": data}
        )
        at.run()
        assert (
            not at.exception
        ), f"render_analyze_card raised for rec={rec}: {at.exception}"

    def test_risk_flags_rendered_as_warnings(self):
        """Two risk flags produce at least two st.warning elements."""
        from streamlit.testing.v1 import AppTest

        data = _make_analyze_response("WATCH")
        at = AppTest.from_function(
            _app_render_card, default_timeout=15, kwargs={"data": data}
        )
        at.run()
        assert not at.exception
        assert len(at.warning) >= 2

    def test_no_risk_flags_no_warnings(self):
        """When risk_flags=[], no warning elements are emitted."""
        from streamlit.testing.v1 import AppTest

        data = _make_analyze_response("HOLD")
        data["risk_flags"] = []
        at = AppTest.from_function(
            _app_render_card, default_timeout=15, kwargs={"data": data}
        )
        at.run()
        assert not at.exception
        assert len(at.warning) == 0

    def test_empty_signals_does_not_crash(self):
        """signals={} renders gracefully without KeyError."""
        from streamlit.testing.v1 import AppTest

        data = _make_analyze_response("BUY")
        data["signals"] = {}
        at = AppTest.from_function(
            _app_render_card, default_timeout=15, kwargs={"data": data}
        )
        at.run()
        assert not at.exception

    def test_missing_targets_does_not_crash(self):
        """targets=[] renders T1/T2 as — without raising."""
        from streamlit.testing.v1 import AppTest

        data = _make_analyze_response("HOLD")
        data["targets"] = []
        at = AppTest.from_function(
            _app_render_card, default_timeout=15, kwargs={"data": data}
        )
        at.run()
        assert not at.exception

    def test_reasoning_expander_present(self):
        """Analyst Thesis expander is present when reasoning is non-empty."""
        from streamlit.testing.v1 import AppTest

        data = _make_analyze_response("BUY")
        at = AppTest.from_function(
            _app_render_card, default_timeout=15, kwargs={"data": data}
        )
        at.run()
        assert not at.exception
        labels = [e.label for e in at.expander]
        assert any(
            "Thesis" in lbl for lbl in labels
        ), f"No Thesis expander, got: {labels}"

    def test_raw_json_expander_present(self):
        """Raw JSON expander is always rendered."""
        from streamlit.testing.v1 import AppTest

        data = _make_analyze_response("BUY")
        at = AppTest.from_function(
            _app_render_card, default_timeout=15, kwargs={"data": data}
        )
        at.run()
        assert not at.exception
        labels = [e.label for e in at.expander]
        assert any("JSON" in lbl for lbl in labels), f"No JSON expander, got: {labels}"

    def test_metrics_rendered(self):
        """Four key metrics (price, R:R, hold period, strategy) appear."""
        from streamlit.testing.v1 import AppTest

        data = _make_analyze_response("BUY")
        at = AppTest.from_function(
            _app_render_card, default_timeout=15, kwargs={"data": data}
        )
        at.run()
        assert not at.exception
        assert len(at.metric) >= 4, f"Expected ≥4 metrics, got {len(at.metric)}"

    def test_unknown_rec_does_not_crash(self):
        """Unknown recommendation type uses fallback colour, no exception."""
        from streamlit.testing.v1 import AppTest

        data = _make_analyze_response("BUY")
        data["recommendation"] = "UNKNOWN_SIGNAL"
        data["risk_flags"] = []
        at = AppTest.from_function(
            _app_render_card, default_timeout=15, kwargs={"data": data}
        )
        at.run()
        assert not at.exception


# ── _render_analyze_result integration tests ─────────────────────────────────


def _app_render_analyze_result_429():
    import sys, os

    sys.path.insert(0, os.path.abspath("src"))
    from unittest.mock import MagicMock, patch

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.json.return_value = {"retry_after_seconds": 30}
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp
    with patch("httpx.Client", return_value=mock_client):
        from plutus.dashboard.analyze_card import render_analyze_result

        render_analyze_result("RELIANCE", "NSE", "http://127.0.0.1:8000", "test-key")


def _app_render_analyze_result_200(data):
    import sys, os

    sys.path.insert(0, os.path.abspath("src"))
    from unittest.mock import MagicMock, patch

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = data
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"X-RateLimit-Remaining": "9"}
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp
    with patch("httpx.Client", return_value=mock_client):
        from plutus.dashboard.analyze_card import render_analyze_result

        render_analyze_result("RELIANCE", "NSE", "http://127.0.0.1:8000", "test-key")


def _app_render_analyze_result_error():
    import sys, os

    sys.path.insert(0, os.path.abspath("src"))
    from unittest.mock import patch

    with patch("httpx.Client", side_effect=Exception("connection refused")):
        from plutus.dashboard.analyze_card import render_analyze_result

        render_analyze_result("RELIANCE", "NSE", "http://127.0.0.1:8000", "test-key")


class TestRenderAnalyzeResult:
    def test_rate_limit_shows_warning(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_function(_app_render_analyze_result_429, default_timeout=15)
        at.run()
        assert not at.exception
        assert len(at.warning) >= 1

    def test_successful_response_renders_card(self):
        from streamlit.testing.v1 import AppTest

        data = _make_analyze_response("BUY")
        at = AppTest.from_function(
            _app_render_analyze_result_200, default_timeout=15, kwargs={"data": data}
        )
        at.run()
        assert not at.exception
        assert len(at.metric) >= 4
        labels = [e.label for e in at.expander]
        assert any("JSON" in lbl for lbl in labels), f"No JSON expander: {labels}"

    def test_http_error_shows_error_not_crash(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_function(_app_render_analyze_result_error, default_timeout=15)
        at.run()
        assert not at.exception
        assert len(at.error) >= 1


# ── Portfolio tab helper unit tests ──────────────────────────────────────────


class TestPortfolioHelpers:
    """Unit tests for _get_trade_history (in-process, no subprocess)."""

    def test_get_trade_history_returns_empty_for_missing_portfolio(self):
        """No portfolio in DB → returns empty list, no crash."""
        db = MagicMock()
        db.__enter__ = MagicMock(return_value=db)
        db.__exit__ = MagicMock(return_value=False)
        db.query.return_value.order_by.return_value.first.return_value = None
        db.query.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.all.return_value = []
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            None
        )
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
            []
        )
        db.query.return_value.all.return_value = []

        with patch("plutus.db.session.SessionLocal", return_value=db):
            from plutus.dashboard.portfolio_helpers import get_trade_history

            result = get_trade_history("ghost_port")

        assert result == []

    def test_get_trade_history_maps_closed_trades_to_dicts(self):
        """Closed trades are mapped to expected dict keys."""
        from plutus.db.models import (
            PaperTrade,
            TradeStatus,
            TradeDirection,
            TradeExitReason,
        )
        from datetime import date

        port = _make_mock_portfolio()

        trade = MagicMock(spec=PaperTrade)
        trade.symbol = "INFY"
        trade.direction = TradeDirection.LONG
        trade.entry_price = Decimal("1500.00")
        trade.entry_date = date(2026, 5, 1)
        trade.exit_price = Decimal("1600.00")
        trade.exit_date = date(2026, 5, 10)
        trade.shares = 10
        trade.realised_pnl = Decimal("1000.00")
        trade.realised_pnl_pct = Decimal("6.67")
        trade.exit_reason = TradeExitReason.TARGET1
        trade.status = TradeStatus.CLOSED

        db = MagicMock()
        db.__enter__ = MagicMock(return_value=db)
        db.__exit__ = MagicMock(return_value=False)
        db.query.return_value.order_by.return_value.first.return_value = None
        db.query.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        db.query.return_value.filter.return_value.first.return_value = port
        db.query.return_value.filter.return_value.all.return_value = []
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            port
        )
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            trade
        ]
        db.query.return_value.all.return_value = [port]

        with patch("plutus.db.session.SessionLocal", return_value=db):
            from plutus.dashboard.portfolio_helpers import get_trade_history

            result = get_trade_history("test_port")

        assert len(result) == 1
        row = result[0]
        expected_keys = {
            "symbol",
            "side",
            "entry_price",
            "entry_date",
            "exit_price",
            "exit_date",
            "shares",
            "realised_pnl",
            "realised_pnl_pct",
            "exit_reason",
        }
        assert expected_keys.issubset(row.keys())
        assert row["symbol"] == "INFY"
        assert row["realised_pnl"] == Decimal("1000.00")


# ── Dashboard full smoke tests ────────────────────────────────────────────────


class TestDashboardSmoke:
    """AppTest.from_file smoke tests for the full dashboard."""

    def test_dashboard_loads_no_portfolios(self):
        """Empty DB → no crash, create-portfolio expander shown."""
        from streamlit.testing.v1 import AppTest

        db = MagicMock()
        db.__enter__ = MagicMock(return_value=db)
        db.__exit__ = MagicMock(return_value=False)
        db.query.return_value.order_by.return_value.first.return_value = None
        db.query.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            None
        )
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
            []
        )
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.all.return_value = []
        db.query.return_value.all.return_value = []

        with (
            patch("plutus.db.session.SessionLocal", return_value=db),
            patch(
                "plutus.backtesting.paper_trader.fetch_live_price", return_value=100.0
            ),
        ):
            at = AppTest.from_file(_app_path(), default_timeout=30)
            at.run()

        assert not at.exception, f"Dashboard crash: {at.exception}"

    def test_dashboard_loads_with_portfolio(self):
        """Dashboard renders without crash when one portfolio exists."""
        from streamlit.testing.v1 import AppTest

        port = _make_mock_portfolio()
        db = MagicMock()
        db.__enter__ = MagicMock(return_value=db)
        db.__exit__ = MagicMock(return_value=False)
        db.query.return_value.order_by.return_value.first.return_value = None
        db.query.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            port
        )
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
            []
        )
        db.query.return_value.filter.return_value.first.return_value = port
        db.query.return_value.filter.return_value.all.return_value = []
        db.query.return_value.all.return_value = [port]

        # Must patch both SessionLocal references: dashboard's and paper_trader's
        with (
            patch("plutus.db.session.SessionLocal", return_value=db),
            patch("plutus.backtesting.paper_trader.SessionLocal", return_value=db),
            patch("dashboard.SessionLocal", return_value=db),
            patch(
                "plutus.backtesting.paper_trader.fetch_live_price", return_value=2800.0
            ),
        ):
            at = AppTest.from_file(_app_path(), default_timeout=30)
            at.run()

        assert not at.exception, f"Dashboard crash with portfolio: {at.exception}"
