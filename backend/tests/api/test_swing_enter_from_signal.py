from __future__ import annotations

from fastapi.testclient import TestClient


def test_enter_from_signal_creates_trade_and_fill(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """POST /swing/signals/{id}/enter must create a SwingTrade + REAL Fill."""
    body = {"side": "BUY", "qty": 50, "price": "1510.00"}
    resp = client.post("/swing/signals/1/enter", json=body, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["kind"] == "REAL"
    assert out["side"] == "BUY"
    assert out["price"] == "1510.00"
    assert out["qty"] == 50
    # The fill should belong to a newly created trade (id > 3 since seed has 3 trades)
    assert out["trade_id"] is not None

    # Confirm the new trade appears in /positions
    positions = client.get("/swing/positions", headers=auth_headers).json()
    new_trade_id = out["trade_id"]
    assert any(p["id"] == new_trade_id for p in positions)


def test_enter_from_signal_unknown_signal_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = {"side": "BUY", "qty": 1, "price": "100.00"}
    resp = client.post("/swing/signals/9999/enter", json=body, headers=auth_headers)
    assert resp.status_code == 404


def test_enter_from_signal_defaults_cost_inr_to_zero(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """cost_inr is optional; omitting it should not cause a 422."""
    body = {"side": "BUY", "qty": 10, "price": "1500.00"}
    resp = client.post("/swing/signals/1/enter", json=body, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cost_inr"] == "0"


def test_enter_from_signal_persists_to_db(client: TestClient, auth_headers: dict[str, str]) -> None:
    """After entering, the trade must be visible in GET /swing/positions."""
    body = {"side": "BUY", "qty": 25, "price": "1505.50"}
    fill_resp = client.post("/swing/signals/1/enter", json=body, headers=auth_headers)
    assert fill_resp.status_code == 200
    trade_id = fill_resp.json()["trade_id"]

    positions = client.get("/swing/positions", headers=auth_headers).json()
    trade_ids = [p["id"] for p in positions]
    assert trade_id in trade_ids, f"trade {trade_id} not found in positions {trade_ids}"
