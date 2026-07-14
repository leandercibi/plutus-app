from __future__ import annotations

from fastapi.testclient import TestClient


def test_pit_universe_past_date(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/shared/universe?as_of=2024-01-01", headers=auth_headers)
    assert resp.status_code == 200
    assert sorted(resp.json()) == ["INFY", "TCS"]


def test_pit_universe_recent_date_differs(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/shared/universe?as_of=2025-01-06", headers=auth_headers)
    assert resp.status_code == 200
    members = sorted(resp.json())
    assert members == ["INFY", "RELIANCE", "TCS"]
    # excluded (in_universe=False) member is absent
    assert "PENNY" not in members


def test_pit_membership_frozen_per_date(client: TestClient, auth_headers: dict[str, str]) -> None:
    past = client.get("/shared/universe?as_of=2024-01-01", headers=auth_headers).json()
    recent = client.get("/shared/universe?as_of=2025-01-06", headers=auth_headers).json()
    assert set(past) != set(recent)
