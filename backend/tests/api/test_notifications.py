from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from plutus.db.models import Notification


@pytest.fixture
def _seed_notifications(session_factory: sessionmaker[Session]) -> None:
    s = session_factory()
    s.add(Notification(
        kind="SL_PROXIMITY",
        severity="WARNING",
        title="INFY near stop loss",
        body="Price ₹1,480 is 2.5% from SL ₹1,444",
        symbol="INFY",
        dismissed=False,
        created_at=datetime(2026, 6, 19, 10, 0),
    ))
    s.add(Notification(
        kind="T1_PROXIMITY",
        severity="INFO",
        title="TCS approaching T1",
        body="Price ₹3,900 is 1.2% from T1 ₹3,948",
        symbol="TCS",
        dismissed=False,
        created_at=datetime(2026, 6, 19, 11, 0),
    ))
    s.add(Notification(
        kind="PNL_UPDATE",
        severity="INFO",
        title="Portfolio P/L update",
        body="Total P/L: +₹1,200 (+0.8%)",
        symbol=None,
        dismissed=True,
        created_at=datetime(2026, 6, 19, 9, 0),
    ))
    s.commit()
    s.close()


@pytest.mark.usefixtures("_seed_notifications")
def test_list_notifications_excludes_dismissed(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/shared/notifications", headers=auth_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert all(not n["dismissed"] for n in items)
    assert items[0]["title"] == "TCS approaching T1"
    assert items[1]["title"] == "INFY near stop loss"


@pytest.mark.usefixtures("_seed_notifications")
def test_list_notifications_includes_dismissed(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get(
        "/shared/notifications",
        headers=auth_headers,
        params={"include_dismissed": "true"},
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 3


@pytest.mark.usefixtures("_seed_notifications")
def test_dismiss_notification_marks_as_dismissed(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    items = client.get("/shared/notifications", headers=auth_headers).json()
    nid = items[0]["id"]
    r = client.post(f"/shared/notifications/{nid}/dismiss", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"
    remaining = client.get("/shared/notifications", headers=auth_headers).json()
    assert len(remaining) == 1


@pytest.mark.usefixtures("_seed_notifications")
def test_notification_has_expected_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    items = client.get("/shared/notifications", headers=auth_headers).json()
    n = items[0]
    assert "id" in n
    assert "kind" in n
    assert "severity" in n
    assert "title" in n
    assert "body" in n
    assert "created_at" in n
    assert "dismissed" in n
