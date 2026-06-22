from __future__ import annotations

from fastapi.testclient import TestClient


def test_filter_by_label_buy(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/swing/signals?label=BUY", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "INFY"
    assert rows[0]["label"] == "BUY"
    # pillar breakdown + calibration band present
    assert rows[0]["pillar_breakdown"]["technical"] == 24
    assert rows[0]["calibration_band"] == "high"
    # decimals as strings
    assert rows[0]["entry"] == "1500.50"


def test_filter_by_run_id(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/swing/signals?run_id=run-1", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_single_signal(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/swing/signals/1", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == 1


def test_get_missing_signal_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/swing/signals/9999", headers=auth_headers)
    assert resp.status_code == 404
