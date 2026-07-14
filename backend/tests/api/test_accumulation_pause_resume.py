from __future__ import annotations

from fastapi.testclient import TestClient


def _position_id(client: TestClient, headers: dict[str, str]) -> int:
    positions = client.get("/accumulation/positions", headers=headers).json()
    return int(positions[0]["id"])


def test_pause_then_resume(client: TestClient, auth_headers: dict[str, str]) -> None:
    pid = _position_id(client, auth_headers)
    paused = client.post(
        f"/accumulation/positions/{pid}/pause",
        json={"reason": "thesis re-check"},
        headers=auth_headers,
    )
    assert paused.status_code == 200
    assert paused.json()["state"] == "PAUSED"

    resumed = client.post(f"/accumulation/positions/{pid}/resume", headers=auth_headers)
    assert resumed.status_code == 200
    assert resumed.json()["state"] == "BUILDING"


def test_resume_requires_prior_pause(client: TestClient, auth_headers: dict[str, str]) -> None:
    pid = _position_id(client, auth_headers)
    # not paused -> resume is a conflict
    resp = client.post(f"/accumulation/positions/{pid}/resume", headers=auth_headers)
    assert resp.status_code == 409


def test_pause_unknown_position_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/accumulation/positions/9999/pause",
        json={"reason": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
