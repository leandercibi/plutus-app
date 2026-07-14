from __future__ import annotations

from fastapi.testclient import TestClient


def test_runs_sunday_returns_run_id(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post("/shared/runs/sunday", headers=auth_headers)
    assert resp.status_code == 200
    assert "run_id" in resp.json()
    assert resp.json()["run_id"]


def test_runs_sunday_idempotency_key_honored(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    headers = {**auth_headers, "Idempotency-Key": "abc-123"}
    first = client.post("/shared/runs/sunday", headers=headers).json()["run_id"]
    second = client.post("/shared/runs/sunday", headers=headers).json()["run_id"]
    assert first == second


def test_runs_sunday_different_keys_differ(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    a = client.post(
        "/shared/runs/sunday", headers={**auth_headers, "Idempotency-Key": "k1"}
    ).json()["run_id"]
    b = client.post(
        "/shared/runs/sunday", headers={**auth_headers, "Idempotency-Key": "k2"}
    ).json()["run_id"]
    assert a != b


def test_midweek_mini_gated_off_returns_409(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post("/shared/runs/midweek-mini", headers=auth_headers)
    assert resp.status_code == 409
