"""Tests for API routes (src/plutus/api/routes.py)."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, date

from plutus.api.routes import router
from plutus.db.models import WeeklyRun, Recommendation, RecommendationVerdict
from fastapi import FastAPI


@pytest.fixture
def app():
    """Create FastAPI app with routes."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def valid_api_key():
    """Set valid API key in settings."""
    test_key = "test-secret-key"
    # Patch the settings object directly since it's already imported
    with patch("plutus.api.routes.settings") as mock_settings:
        mock_settings.API_SECRET_KEY = test_key
        yield test_key


@pytest.fixture
def mock_analysis_result():
    """Mock successful analysis result from run_analysis."""
    return {
        "current_price": 2465.0,
        "recommendation": "BUY",
        "confidence": 8.5,
        "entry_zone": [2450.0, 2480.0],
        "targets": [2650.0, 2750.0],
        "stop_loss": 2380.0,
        "risk_reward": 2.5,
        "position": {
            "shares": 40,
            "capital": 98600.0,
            "pct_of_portfolio": 25.0,
            "max_loss_inr": 3400.0,
        },
        "hold_days": "5-8",
        "strategy": "trend",
        "technical_output": {"verdict": "bullish", "score": 7.5},
        "sentiment_output": {"sentiment": "positive", "score": 8.0},
        "smart_money_output": {"signal": "accumulation", "score": 7.0},
        "risk_flags": [],
        "reasoning": "Strong uptrend with volume confirmation",
    }


# ── Authentication Tests ──────────────────────────────────────────────────


def test_analyze_missing_api_key(client):
    """Test /analyze without API key returns 422."""
    response = client.post("/analyze", json={"symbol": "RELIANCE"})
    assert response.status_code == 422


def test_analyze_invalid_api_key(client, valid_api_key):
    """Test /analyze with invalid API key returns 401."""
    response = client.post(
        "/analyze", json={"symbol": "RELIANCE"}, headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401
    assert "Invalid API key" in response.json()["detail"]


def test_weekly_missing_api_key(client):
    """Test /weekly without API key returns 422."""
    response = client.get("/weekly")
    assert response.status_code == 422


def test_weekly_invalid_api_key(client, valid_api_key):
    """Test /weekly with invalid API key returns 401."""
    response = client.get("/weekly", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


def test_health_no_auth_required(client):
    """Test /health endpoint works without authentication."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "Plutus Trading Engine"
    assert "timestamp" in data


# ── /analyze Endpoint Tests ───────────────────────────────────────────────


@patch("plutus.api.routes.run_analysis")
def test_analyze_success(
    mock_run_analysis, client, valid_api_key, mock_analysis_result
):
    """Test successful /analyze request."""
    mock_run_analysis.return_value = mock_analysis_result

    response = client.post(
        "/analyze",
        json={"symbol": "RELIANCE", "exchange": "NSE"},
        headers={"X-API-Key": valid_api_key},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert data["symbol"] == "RELIANCE"
    assert data["exchange"] == "NSE"
    assert data["current_price"] == 2465.0
    assert data["recommendation"] == "BUY"
    assert data["confidence"] == 8.5
    assert data["entry_zone"] == [2450.0, 2480.0]
    assert data["targets"] == [2650.0, 2750.0]
    assert data["stop_loss"] == 2380.0
    assert data["risk_reward"] == 2.5
    assert data["hold_days"] == "5-8"
    assert data["strategy"] == "trend"
    assert data["reasoning"] == "Strong uptrend with volume confirmation"
    assert "analysis_time_sec" in data

    # Verify position details
    assert data["position"]["shares"] == 40
    assert data["position"]["capital"] == 98600.0

    # Verify signals
    assert data["signals"]["technical"]["verdict"] == "bullish"
    assert data["signals"]["sentiment"]["sentiment"] == "positive"
    assert data["signals"]["smart_money"]["signal"] == "accumulation"

    # Verify run_analysis was called correctly
    mock_run_analysis.assert_called_once_with("RELIANCE", "NSE")


@patch("plutus.api.routes.run_analysis")
def test_analyze_symbol_normalization(
    mock_run_analysis, client, valid_api_key, mock_analysis_result
):
    """Test symbol is uppercased and stripped."""
    mock_run_analysis.return_value = mock_analysis_result

    response = client.post(
        "/analyze",
        json={"symbol": "  reliance  ", "exchange": "nse"},
        headers={"X-API-Key": valid_api_key},
    )

    assert response.status_code == 200
    mock_run_analysis.assert_called_once_with("RELIANCE", "NSE")


@patch("plutus.api.routes.run_analysis")
def test_analyze_default_exchange(
    mock_run_analysis, client, valid_api_key, mock_analysis_result
):
    """Test default exchange is NSE."""
    mock_run_analysis.return_value = mock_analysis_result

    response = client.post(
        "/analyze", json={"symbol": "RELIANCE"}, headers={"X-API-Key": valid_api_key}
    )

    assert response.status_code == 200
    mock_run_analysis.assert_called_once_with("RELIANCE", "NSE")


@patch("plutus.api.routes.run_analysis")
def test_analyze_value_error(mock_run_analysis, client, valid_api_key):
    """Test /analyze returns 422 on ValueError."""
    mock_run_analysis.side_effect = ValueError("Invalid symbol")

    response = client.post(
        "/analyze", json={"symbol": "INVALID"}, headers={"X-API-Key": valid_api_key}
    )

    assert response.status_code == 422
    assert "Invalid symbol" in response.json()["detail"]


@patch("plutus.api.routes.run_analysis")
def test_analyze_general_error(mock_run_analysis, client, valid_api_key):
    """Test /analyze returns 503 on general exception."""
    mock_run_analysis.side_effect = Exception("Network timeout")

    response = client.post(
        "/analyze", json={"symbol": "RELIANCE"}, headers={"X-API-Key": valid_api_key}
    )

    assert response.status_code == 503
    assert "Analysis failed" in response.json()["detail"]
    assert "Network timeout" in response.json()["detail"]


@patch("plutus.api.routes.run_analysis")
def test_analyze_missing_optional_fields(mock_run_analysis, client, valid_api_key):
    """Test /analyze handles missing optional fields gracefully."""
    minimal_result = {
        "current_price": 2465.0,
        # All other fields missing
    }
    mock_run_analysis.return_value = minimal_result

    response = client.post(
        "/analyze", json={"symbol": "RELIANCE"}, headers={"X-API-Key": valid_api_key}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recommendation"] == "HOLD"  # default
    assert data["confidence"] == 0  # default
    assert data["entry_zone"] == [0, 0]  # default
    assert data["hold_days"] == "N/A"  # default


# ── /weekly Endpoint Tests ────────────────────────────────────────────────


@patch("plutus.api.routes.SessionLocal")
def test_weekly_success(
    mock_session_local,
    client,
    valid_api_key,
    test_db_session,
    weekly_run_factory,
    recommendation_factory,
):
    """Test successful /weekly request."""
    # Create test data
    run = weekly_run_factory(
        run_date=date(2026, 5, 31),
        market_regime="BULLISH",
        stocks_screened=150,
        total_buy_signals=2,
        total_watch_signals=1,
    )

    rec1 = recommendation_factory(
        symbol="RELIANCE",
        recommendation=RecommendationVerdict.BUY,
        weekly_run_id=run.id,
        confidence=8.5,
    )

    rec2 = recommendation_factory(
        symbol="INFY",
        recommendation=RecommendationVerdict.BUY,
        weekly_run_id=run.id,
        confidence=7.5,
    )

    rec3 = recommendation_factory(
        symbol="TCS",
        recommendation=RecommendationVerdict.WATCH,
        weekly_run_id=run.id,
        confidence=6.5,
    )

    # Mock SessionLocal to return test session
    mock_session_local.return_value.__enter__ = lambda self: test_db_session
    mock_session_local.return_value.__exit__ = lambda self, *args: None

    response = client.get("/weekly", headers={"X-API-Key": valid_api_key})

    assert response.status_code == 200
    data = response.json()

    assert data["run_date"] == "2026-05-31"
    assert data["market_regime"] == "BULLISH"
    assert data["total_screened"] == 150

    # Verify BUY signals (sorted by confidence desc)
    assert len(data["buy_signals"]) == 2
    assert data["buy_signals"][0]["symbol"] == "RELIANCE"
    assert data["buy_signals"][0]["confidence"] == 8.5
    assert data["buy_signals"][1]["symbol"] == "INFY"

    # Verify WATCH signals
    assert len(data["watch_signals"]) == 1
    assert data["watch_signals"][0]["symbol"] == "TCS"


@patch("plutus.api.routes.SessionLocal")
def test_weekly_no_run_found(
    mock_session_local, client, valid_api_key, test_db_session
):
    """Test /weekly returns 404 when no weekly run exists."""
    mock_session_local.return_value.__enter__ = lambda self: test_db_session
    mock_session_local.return_value.__exit__ = lambda self, *args: None

    response = client.get("/weekly", headers={"X-API-Key": valid_api_key})

    assert response.status_code == 404
    assert "No weekly run found" in response.json()["detail"]


@patch("plutus.api.routes.SessionLocal")
def test_weekly_empty_recommendations(
    mock_session_local, client, valid_api_key, test_db_session, weekly_run_factory
):
    """Test /weekly with run but no recommendations."""
    run = weekly_run_factory(
        run_date=date(2026, 5, 31),
        total_buy_signals=0,
        total_watch_signals=0,
    )

    mock_session_local.return_value.__enter__ = lambda self: test_db_session
    mock_session_local.return_value.__exit__ = lambda self, *args: None

    response = client.get("/weekly", headers={"X-API-Key": valid_api_key})

    assert response.status_code == 200
    data = response.json()
    assert len(data["buy_signals"]) == 0
    assert len(data["watch_signals"]) == 0


@patch("plutus.api.routes.SessionLocal")
def test_weekly_filters_only_buy_watch(
    mock_session_local,
    client,
    valid_api_key,
    test_db_session,
    weekly_run_factory,
    recommendation_factory,
):
    """Test /weekly only returns BUY and WATCH recommendations."""
    run = weekly_run_factory()

    recommendation_factory(
        symbol="BUY1", recommendation=RecommendationVerdict.BUY, weekly_run_id=run.id
    )
    recommendation_factory(
        symbol="WATCH1",
        recommendation=RecommendationVerdict.WATCH,
        weekly_run_id=run.id,
    )
    recommendation_factory(
        symbol="HOLD1", recommendation=RecommendationVerdict.HOLD, weekly_run_id=run.id
    )
    recommendation_factory(
        symbol="AVOID1",
        recommendation=RecommendationVerdict.AVOID,
        weekly_run_id=run.id,
    )

    mock_session_local.return_value.__enter__ = lambda self: test_db_session
    mock_session_local.return_value.__exit__ = lambda self, *args: None

    response = client.get("/weekly", headers={"X-API-Key": valid_api_key})

    assert response.status_code == 200
    data = response.json()
    assert len(data["buy_signals"]) == 1
    assert len(data["watch_signals"]) == 1
    assert data["buy_signals"][0]["symbol"] == "BUY1"
    assert data["watch_signals"][0]["symbol"] == "WATCH1"


# ── Response Model Validation ─────────────────────────────────────────────


@patch("plutus.api.routes.run_analysis")
def test_analyze_response_model_validation(
    mock_run_analysis, client, valid_api_key, mock_analysis_result
):
    """Test response matches AnalyzeResponse model."""
    mock_run_analysis.return_value = mock_analysis_result

    response = client.post(
        "/analyze", json={"symbol": "RELIANCE"}, headers={"X-API-Key": valid_api_key}
    )

    assert response.status_code == 200
    data = response.json()

    # Required fields
    required_fields = [
        "symbol",
        "exchange",
        "current_price",
        "recommendation",
        "confidence",
        "entry_zone",
        "targets",
        "stop_loss",
        "risk_reward",
        "position",
        "hold_days",
        "strategy",
        "signals",
        "risk_flags",
        "reasoning",
        "analysis_time_sec",
    ]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"

    # Position sub-model
    position_fields = ["shares", "capital", "pct_of_portfolio", "max_loss_inr"]
    for field in position_fields:
        assert field in data["position"], f"Missing position field: {field}"

    # Signals sub-model
    signal_fields = ["technical", "sentiment", "smart_money"]
    for field in signal_fields:
        assert field in data["signals"], f"Missing signals field: {field}"
