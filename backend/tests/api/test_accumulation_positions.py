from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient


def test_start_position_creates_tranche(client: TestClient, auth_headers: dict[str, str]) -> None:
    r = client.post(
        "/accumulation/positions",
        headers=auth_headers,
        json={"symbol": "CUMMINSIND", "price": "1500.00", "qty": 10},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["symbol"] == "CUMMINSIND"
    assert body["state"] == "BUILDING"
    assert Decimal(body["avg_cost"]) == Decimal("1500.00")
    assert body["qty_total"] == 10


def test_duplicate_position_returns_409(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.post(
        "/accumulation/positions",
        headers=auth_headers,
        json={"symbol": "SOLARINDS", "price": "800.00", "qty": 5},
    )
    r2 = client.post(
        "/accumulation/positions",
        headers=auth_headers,
        json={"symbol": "SOLARINDS", "price": "810.00", "qty": 5},
    )
    assert r2.status_code == 409


def test_log_tranche_updates_avg_cost(client: TestClient, auth_headers: dict[str, str]) -> None:
    r = client.post(
        "/accumulation/positions",
        headers=auth_headers,
        json={"symbol": "MARICO", "price": "600.00", "qty": 10},
    )
    pos_id = r.json()["id"]

    r2 = client.post(
        f"/accumulation/positions/{pos_id}/tranches",
        headers=auth_headers,
        json={"price": "580.00", "qty": 10},
    )
    assert r2.status_code == 201
    assert r2.json()["seq"] == 2

    # Verify weighted average: (600*10 + 580*10) / 20 = 590
    pos_list = client.get("/accumulation/positions", headers=auth_headers).json()
    pos = next(p for p in pos_list if p["id"] == pos_id)
    assert Decimal(pos["avg_cost"]) == Decimal("590.00")
    assert pos["qty_total"] == 20


def test_sixth_tranche_returns_409(client: TestClient, auth_headers: dict[str, str]) -> None:
    r = client.post(
        "/accumulation/positions",
        headers=auth_headers,
        json={"symbol": "PIIND", "price": "3000.00", "qty": 2},
    )
    pos_id = r.json()["id"]
    for _ in range(4):
        client.post(
            f"/accumulation/positions/{pos_id}/tranches",
            headers=auth_headers,
            json={"price": "3000.00", "qty": 2},
        )
    r6 = client.post(
        f"/accumulation/positions/{pos_id}/tranches",
        headers=auth_headers,
        json={"price": "3000.00", "qty": 2},
    )
    assert r6.status_code == 409


def test_exit_position(client: TestClient, auth_headers: dict[str, str]) -> None:
    r = client.post(
        "/accumulation/positions",
        headers=auth_headers,
        json={"symbol": "ADANIPORTS", "price": "1200.00", "qty": 8},
    )
    pos_id = r.json()["id"]

    r_exit = client.post(
        f"/accumulation/positions/{pos_id}/exit",
        headers=auth_headers,
        json={"price": "1300.00", "qty": 8, "reason": "target hit"},
    )
    assert r_exit.status_code == 200
    assert r_exit.json()["state"] == "EXITED"


def test_exit_already_exited_returns_409(client: TestClient, auth_headers: dict[str, str]) -> None:
    r = client.post(
        "/accumulation/positions",
        headers=auth_headers,
        json={"symbol": "APOLLOHOSP", "price": "6000.00", "qty": 3},
    )
    pos_id = r.json()["id"]
    client.post(
        f"/accumulation/positions/{pos_id}/exit",
        headers=auth_headers,
        json={"price": "6100.00", "qty": 3},
    )
    r2 = client.post(
        f"/accumulation/positions/{pos_id}/exit",
        headers=auth_headers,
        json={"price": "6100.00", "qty": 3},
    )
    assert r2.status_code == 409
