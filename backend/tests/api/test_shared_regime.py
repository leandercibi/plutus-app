from __future__ import annotations

from fastapi.testclient import TestClient


def test_latest_regime_returns_most_recent(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/shared/regime", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["as_of_date"] == "2025-01-06"
    assert body["label"] == "BULL"
    assert body["breadth_confirmed_flip"] is True


def test_regime_history_returns_list(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/shared/regime/history?days=30", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    # most recent first
    assert rows[0]["as_of_date"] == "2025-01-06"
    # decimals serialized as strings
    assert rows[0]["nifty_close"] == "22500.00"
