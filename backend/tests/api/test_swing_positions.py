from __future__ import annotations

from fastapi.testclient import TestClient


def test_positions_include_open_and_recent_closed(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/swing/positions", headers=auth_headers)
    assert resp.status_code == 200
    symbols = {r["symbol"] for r in resp.json()}
    # open INFY + recently-closed TCS present; old OLDCO excluded
    assert "INFY" in symbols
    assert "TCS" in symbols
    assert "OLDCO" not in symbols
