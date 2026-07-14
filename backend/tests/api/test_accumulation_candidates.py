from __future__ import annotations

from fastapi.testclient import TestClient


def test_candidates_schema_and_hard_avoid(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/accumulation/candidates?run_id=run-1", headers=auth_headers)
    assert resp.status_code == 200
    rows = {r["symbol"]: r for r in resp.json()}
    assert rows["HDFCBANK"]["hard_avoid_active"] is False
    assert rows["VALUETRAP"]["hard_avoid_active"] is True
    assert rows["HDFCBANK"]["rs_30"] == 0.68
    assert rows["HDFCBANK"]["cagr_eps_3y"] == 0.15


def test_candidates_all_when_no_run_filter(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/accumulation/candidates", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2
