from __future__ import annotations

from fastapi.testclient import TestClient


def _position_id(client: TestClient, headers: dict[str, str]) -> int:
    positions = client.get("/accumulation/positions", headers=headers).json()
    return int(positions[0]["id"])


def test_tranches_ordered_by_seq(client: TestClient, auth_headers: dict[str, str]) -> None:
    pid = _position_id(client, auth_headers)
    resp = client.get(f"/accumulation/positions/{pid}/tranches", headers=auth_headers)
    assert resp.status_code == 200
    seqs = [t["seq"] for t in resp.json()]
    assert seqs == sorted(seqs)
    assert seqs == [1, 2, 3]


def test_tranche_decimal_serialized_as_string(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    pid = _position_id(client, auth_headers)
    rows = client.get(f"/accumulation/positions/{pid}/tranches", headers=auth_headers).json()
    filled = next(t for t in rows if t["seq"] == 1)
    assert filled["filled_at_price"] == "1650.00"
    empty = next(t for t in rows if t["seq"] == 3)
    assert empty["filled_at_price"] is None
