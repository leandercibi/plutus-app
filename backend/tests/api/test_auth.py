from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import TEST_TOKEN


def test_healthz_unauthenticated(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_version_unauthenticated(client: TestClient) -> None:
    resp = client.get("/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_missing_bearer_rejected(client: TestClient) -> None:
    resp = client.get("/shared/regime")
    assert resp.status_code == 401


def test_wrong_bearer_rejected(client: TestClient) -> None:
    resp = client.get("/shared/regime", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_correct_bearer_allowed(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/shared/regime", headers=auth_headers)
    assert resp.status_code == 200


def test_token_matches_fixture() -> None:
    assert TEST_TOKEN == "test-operator-token"
