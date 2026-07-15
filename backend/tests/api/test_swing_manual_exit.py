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


# --- realised-R accumulation (regression: full/partial closes must move the
# needle on trade.realized_R, else Dashboard "Realised" and postmortem stay 0) ---


def test_manual_exit_full_credits_r_multiple(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # Seeded trade 1: INFY, qty=100, risk_R=1.0, entry fill @ ₹1501.
    # Full exit @ ₹1503 → R-multiple = (1503-1501)/1.0 = 2.0R, qty ratio 1.0 → +2.0R.
    resp = client.post(
        "/swing/trades/1/exit/manual",
        json={"reason": "manual", "price": "1503.00"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["state"] == "CLOSED_WIN"
    assert out["realized_R"] == 2.0


def test_manual_exit_partial_credits_proportional_r(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # Sell 25 of 100 @ ₹1503 → 2R × (25/100) = 0.5R. Trade stays OPEN.
    resp = client.post(
        "/swing/trades/1/exit/manual",
        json={"reason": "trim", "qty": 25, "price": "1503.00"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["state"] == "OPEN"
    assert out["qty"] == 75
    assert out["realized_R"] == 0.5


def test_manual_exit_partials_accumulate(client: TestClient, auth_headers: dict[str, str]) -> None:
    # Two partial sells + one final should sum to the full-position R.
    first = client.post(
        "/swing/trades/1/exit/manual",
        json={"reason": "trim1", "qty": 30, "price": "1503.00"},
        headers=auth_headers,
    )
    assert first.status_code == 200 and first.json()["realized_R"] == 0.6  # 2R × 0.3
    second = client.post(
        "/swing/trades/1/exit/manual",
        json={"reason": "trim2", "qty": 20, "price": "1501.00"},
        headers=auth_headers,
    )
    # 0R × 0.2 → running 0.6R, still OPEN
    assert second.status_code == 200 and second.json()["realized_R"] == 0.6
    final = client.post(
        "/swing/trades/1/exit/manual",
        json={"reason": "close", "price": "1502.00"},
        headers=auth_headers,
    )
    # 1R × (50/100) = 0.5R → total 1.1R, CLOSED_WIN
    assert final.status_code == 200
    out = final.json()
    assert out["state"] == "CLOSED_WIN"
    assert abs(out["realized_R"] - 1.1) < 1e-9


def test_manual_exit_loss_marks_closed_loss(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # Full exit below entry → negative realized_R → CLOSED_LOSS.
    resp = client.post(
        "/swing/trades/1/exit/manual",
        json={"reason": "sl", "price": "1500.00"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["state"] == "CLOSED_LOSS"
    assert out["realized_R"] == -1.0  # (1500-1501)/1.0 × 1.0
