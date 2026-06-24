from __future__ import annotations

from fastapi.testclient import TestClient


def test_calibration_returns_ci_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/shared/calibration/trend_70_75/BULL", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["bucket"] == "trend_70_75"
    assert body["regime"] == "BULL"
    assert body["ci_low_R"] == 0.2
    assert body["ci_high_R"] == 0.7
    assert body["confidence_band"] == "high"
    assert body["sprt_state"] == "continue"


def test_calibration_missing_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/shared/calibration/nope/BULL", headers=auth_headers)
    assert resp.status_code == 404
