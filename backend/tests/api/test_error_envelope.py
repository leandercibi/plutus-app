from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from plutus.api.deps import get_app_settings, get_db
from plutus.api.main import create_app
from plutus.config.settings import Settings
from tests.api.conftest import TEST_TOKEN


def test_http_exception_returns_error_envelope(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/swing/signals/9999", headers=auth_headers)
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "request_id"}
    assert body["code"] == "http_404"
    assert body["request_id"]


def test_unhandled_exception_returns_sanitized_500(
    session_factory: sessionmaker[Session], settings: Settings
) -> None:
    app = create_app()

    def _boom() -> Iterator[Session]:
        raise RuntimeError("secret internal detail that must not leak")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = _boom
    app.dependency_overrides[get_app_settings] = lambda: settings
    # do not raise server exceptions so the handler is exercised
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get(
            "/shared/regime", headers={"Authorization": f"Bearer {TEST_TOKEN}"}
        )
    assert resp.status_code == 500
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "request_id"}
    assert body["code"] == "internal_error"
    assert "secret internal detail" not in body["message"]
    assert "Traceback" not in body["message"]
