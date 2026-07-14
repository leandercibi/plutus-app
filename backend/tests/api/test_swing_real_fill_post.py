from __future__ import annotations

from fastapi.testclient import TestClient


def test_post_real_fill_returned(client: TestClient, auth_headers: dict[str, str]) -> None:
    body = {
        "side": "BUY",
        "qty": 100,
        "price": "1502.25",
        "cost_inr": "131.00",
        "filled_at": "2025-01-06T09:31:00",
    }
    resp = client.post("/swing/trades/1/fills/real", json=body, headers=auth_headers)
    assert resp.status_code == 200
    out = resp.json()
    assert out["kind"] == "REAL"
    assert out["side"] == "BUY"
    assert out["price"] == "1502.25"
    assert out["trade_id"] == 1


def test_post_real_fill_persists_alongside_mock(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = {
        "side": "BUY",
        "qty": 100,
        "price": "1502.25",
        "cost_inr": "131.00",
        "filled_at": "2025-01-06T09:31:00",
    }
    client.post("/swing/trades/1/fills/real", json=body, headers=auth_headers)
    # second post adds another REAL fill without error (mock preserved separately)
    resp = client.post("/swing/trades/1/fills/real", json=body, headers=auth_headers)
    assert resp.status_code == 200


def test_post_real_fill_unknown_trade_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    body = {
        "side": "BUY",
        "qty": 1,
        "price": "1.00",
        "cost_inr": "0.10",
        "filled_at": "2025-01-06T09:31:00",
    }
    resp = client.post("/swing/trades/9999/fills/real", json=body, headers=auth_headers)
    assert resp.status_code == 404
