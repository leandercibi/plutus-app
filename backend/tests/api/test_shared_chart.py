from __future__ import annotations

from datetime import date, timedelta
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
def test_chart_returns_bars_and_latest_price(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/shared/chart/INFY", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "INFY"
    assert body["latest_price"] > 0
    assert isinstance(body["bars"], list)
    assert len(body["bars"]) > 0
    bar = body["bars"][-1]
    assert "close" in bar
    assert "dma20" in bar


@pytest.mark.usefixtures("_mock_yfinance")
def test_chart_includes_dma_values(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/shared/chart/INFY", headers=auth_headers)
    bars = r.json()["bars"]
    last = bars[-1]
    assert last["dma20"] is not None
    assert last["dma50"] is not None


@pytest.mark.usefixtures("_mock_yfinance")
def test_chart_with_signal_id_includes_marker(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/shared/chart/INFY?signal_id=1", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["signal_marker"] is not None
    assert body["signal_marker"]["bundle"] == "trend"
    assert body["signal_marker"]["entry"] > 0


@pytest.mark.usefixtures("_mock_yfinance")
def test_chart_without_signal_has_no_marker(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/shared/chart/INFY", headers=auth_headers)
    assert r.json()["signal_marker"] is None


@pytest.mark.usefixtures("_mock_yfinance")
def test_chart_latest_change_pct(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/shared/chart/INFY", headers=auth_headers)
    body = r.json()
    assert isinstance(body["latest_change_pct"], float)
