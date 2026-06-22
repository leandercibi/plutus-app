from __future__ import annotations

from fastapi.testclient import TestClient


def test_cooldowns_separate_rows_per_kind(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/swing/cooldowns/INFY", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    kinds = {r["kind"] for r in rows}
    # A16: SL_WARNING and SL_BREACH are independent rows
    assert kinds == {"SL_WARNING", "SL_BREACH"}


def test_cooldowns_unknown_symbol_empty(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/swing/cooldowns/NOSUCH", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []
