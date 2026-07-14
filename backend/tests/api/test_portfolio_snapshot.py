from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient


def _fake_ohlcv(symbol: str, start: date, end: date) -> pd.DataFrame:
    dates = pd.date_range(start=start, end=end, freq="B")
    n = len(dates)
    base = 1500.0
    return pd.DataFrame(
        {
            "date": dates,
            "open": [base + i for i in range(n)],
            "high": [base + i + 5 for i in range(n)],
            "low": [base + i - 5 for i in range(n)],
            "close": [base + i + 1 for i in range(n)],
            "volume": [1_000_000] * n,
        }
    )


@pytest.fixture
def _mock_yfinance():
    with patch(
        "plutus.data.providers.yfinance_provider.YFinanceProvider.fetch",
        side_effect=_fake_ohlcv,
    ) as m:
        yield m


@pytest.mark.usefixtures("_mock_yfinance")
def test_portfolio_snapshot_returns_positions(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/shared/portfolio-snapshot", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["positions"], list)
    assert body["total_invested"] > 0
    assert "checked_at" in body
    symbols = {p["symbol"] for p in body["positions"]}
    assert "INFY" in symbols
    for pos in body["positions"]:
        assert "current_price" in pos
        assert "pnl" in pos
        assert "pnl_pct" in pos


@pytest.mark.usefixtures("_mock_yfinance")
def test_hourly_check_creates_no_notifications_when_no_trades(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.post("/shared/portfolio-snapshot/check", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["notifications_created"] == 0


@pytest.mark.usefixtures("_mock_yfinance")
def test_list_notifications_returns_empty_initially(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/shared/notifications", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.usefixtures("_mock_yfinance")
def test_portfolio_snapshot_stores_latest_prices(
    client: TestClient,
    auth_headers: dict[str, str],
    session_factory,
) -> None:
    from plutus.db.models import LatestPrice

    client.get("/shared/portfolio-snapshot", headers=auth_headers)
    s = session_factory()
    rows = s.query(LatestPrice).all()
    s.close()
    assert len(rows) > 0
    for row in rows:
        assert row.price > 0
        assert row.source in ("angelone", "yfinance")


def test_dismiss_nonexistent_notification_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.post("/shared/notifications/99999/dismiss", headers=auth_headers)
    assert r.status_code == 404
