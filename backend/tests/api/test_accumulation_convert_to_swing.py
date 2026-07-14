from __future__ import annotations

from fastapi.testclient import TestClient


def _position_id(client: TestClient, headers: dict[str, str]) -> int:
    positions = client.get("/accumulation/positions", headers=headers).json()
    return int(positions[0]["id"])


def test_convert_creates_swing_trade(client: TestClient, auth_headers: dict[str, str]) -> None:
    pid = _position_id(client, auth_headers)
    resp = client.post(f"/accumulation/positions/{pid}/convert-to-swing", headers=auth_headers)
    assert resp.status_code == 200
    trade = resp.json()
    assert trade["symbol"] == "HDFCBANK"
    assert trade["state"] == "OPEN"
    assert trade["bundle"] == "bull_ready"


def test_convert_sets_position_state(client: TestClient, auth_headers: dict[str, str]) -> None:
    pid = _position_id(client, auth_headers)
    client.post(f"/accumulation/positions/{pid}/convert-to-swing", headers=auth_headers)
    positions = client.get("/accumulation/positions", headers=auth_headers).json()
    converted = next(p for p in positions if p["id"] == pid)
    assert converted["state"] == "CONVERTED_TO_SWING"


def test_convert_twice_conflicts(client: TestClient, auth_headers: dict[str, str]) -> None:
    pid = _position_id(client, auth_headers)
    client.post(f"/accumulation/positions/{pid}/convert-to-swing", headers=auth_headers)
    resp = client.post(f"/accumulation/positions/{pid}/convert-to-swing", headers=auth_headers)
    assert resp.status_code == 409
