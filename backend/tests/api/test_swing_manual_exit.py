from __future__ import annotations

from fastapi.testclient import TestClient


def test_manual_exit_updates_state(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/swing/trades/1/exit/manual",
        json={"reason": "operator close"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["state"] in ("CLOSED_WIN", "CLOSED_LOSS")
    assert out["closed_at"] is not None
    assert out["exit_reason"] == "operator close"


def test_manual_exit_does_not_error_or_refire(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # No alert side-effect path; calling twice simply re-closes without raising.
    first = client.post("/swing/trades/1/exit/manual", json={"reason": "x"}, headers=auth_headers)
    second = client.post("/swing/trades/1/exit/manual", json={"reason": "y"}, headers=auth_headers)
    assert first.status_code == 200
    assert second.status_code == 200


def test_manual_exit_unknown_trade_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post("/swing/trades/9999/exit/manual", json={"reason": "x"}, headers=auth_headers)
    assert resp.status_code == 404
