from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient


def test_signal_decimals_are_strings_and_reparse(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = client.get("/swing/signals/1", headers=auth_headers).json()
    for field in ("entry", "stop_loss", "target_1", "target_2"):
        assert isinstance(body[field], str)
    # lossless re-parse
    assert Decimal(body["entry"]) == Decimal("1500.50")
    assert Decimal(body["stop_loss"]) == Decimal("1450.00")


def test_regime_decimals_are_strings(client: TestClient, auth_headers: dict[str, str]) -> None:
    rows = client.get("/shared/regime/history?days=5", headers=auth_headers).json()
    assert isinstance(rows[0]["nifty_close"], str)
    assert Decimal(rows[0]["nifty_close"]) == Decimal("22500.00")


def test_position_avg_cost_is_string(client: TestClient, auth_headers: dict[str, str]) -> None:
    positions = client.get("/accumulation/positions", headers=auth_headers).json()
    assert isinstance(positions[0]["avg_cost"], str)
    assert Decimal(positions[0]["avg_cost"]) == Decimal("1650.00")
