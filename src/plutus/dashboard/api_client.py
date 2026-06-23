from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import requests

from plutus.config.settings import get_settings

_DEFAULT_BASE = "http://localhost:8009"


def _base() -> str:
    return os.environ.get("PLUTUS_API_URL", _DEFAULT_BASE)


def _headers() -> dict[str, str]:
    token = get_settings().api_token
    if token is not None:
        return {"Authorization": f"Bearer {token.get_secret_value()}"}
    return {}


def _post(path: str, json: dict | None = None, timeout: int = 10) -> requests.Response:
    return requests.post(
        f"{_base()}{path}", headers=_headers(), json=json, timeout=timeout
    )


def _get(path: str, timeout: int = 10) -> requests.Response:
    return requests.get(f"{_base()}{path}", headers=_headers(), timeout=timeout)


def _repo_root() -> Path:
    # src/plutus/dashboard/api_client.py → repo root is 4 levels up.
    return Path(__file__).resolve().parents[3]


def trigger_sunday_run() -> str:
    """Run the full Sunday pipeline as a detached subprocess.

    Generates a run_id up-front and passes it to the script via --run-id so the
    id surfaced to the user matches the row in `db.run_log` and the signals'
    `run_id` column. Returns that id immediately; the run continues in the
    background.
    """
    import uuid

    repo = _repo_root()
    script = repo / "scripts" / "run_pipeline.py"
    if not script.exists():
        raise RuntimeError(f"run_pipeline.py not found at {script}")
    logs_dir = repo / "logs"
    logs_dir.mkdir(exist_ok=True)
    run_id = f"sun-{uuid.uuid4().hex[:8]}"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = logs_dir / f"sunday-{ts}-{run_id}.log"
    with open(log_path, "w") as logf:
        subprocess.Popen(
            [sys.executable, str(script), "--run-id", run_id],
            cwd=str(repo),
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
    return run_id


def trigger_monday_reval() -> str:
    """Re-validation requires the API (it reads Sunday's signal set and re-runs
    entry gates). Fallback when API is down: tell the user clearly."""
    try:
        r = _post("/shared/runs/monday-revalidation", timeout=5)
        r.raise_for_status()
        return r.json().get("run_id", "")
    except requests.RequestException as e:
        raise RuntimeError(
            "Monday re-validation needs the API. Start it with:\n"
            "  uvicorn plutus.api.main:app --port 8009\n"
            f"(connection error: {e})"
        ) from e


def test_telegram() -> str:
    r = _post("/shared/test-telegram")
    if r.status_code == 200:
        return "ok"
    return f"error {r.status_code}: {r.text[:100]}"


def log_real_fill(
    trade_id: int,
    side: str,
    qty: int,
    price: Decimal | float,
    filled_at: datetime | None = None,
    cost_inr: Decimal | float = 0,
) -> tuple[bool, str]:
    payload = {
        "side": side,
        "qty": qty,
        "price": str(price),
        "cost_inr": str(cost_inr),
        "filled_at": (filled_at or datetime.now()).isoformat(),
    }
    try:
        r = _post(f"/swing/trades/{trade_id}/fills/real", json=payload)
        if r.status_code == 200:
            return True, "fill logged"
        return False, f"error {r.status_code}: {r.text[:120]}"
    except requests.RequestException as e:
        return False, f"network error: {e}"


def enter_from_signal(
    signal_id: int,
    side: str,
    qty: int,
    price: Decimal | float,
    filled_at: datetime | None = None,
) -> tuple[bool, str]:
    """Create a trade + entry fill from a signal id in one shot."""
    payload = {
        "side": side,
        "qty": qty,
        "price": str(price),
        "cost_inr": "0",
        "filled_at": (filled_at or datetime.now()).isoformat(),
    }
    try:
        r = _post(f"/swing/signals/{signal_id}/enter", json=payload)
        if r.status_code == 200:
            return True, "trade opened and fill logged"
        return False, f"error {r.status_code}: {r.text[:120]}"
    except requests.RequestException as e:
        return False, f"network error: {e}"


def manual_exit(
    trade_id: int,
    reason: str,
    qty: int | None = None,
    price: float | None = None,
) -> tuple[bool, str]:
    payload: dict = {"reason": reason}
    if qty is not None:
        payload["qty"] = qty
    if price is not None:
        payload["price"] = str(price)
    try:
        r = _post(f"/swing/trades/{trade_id}/exit/manual", json=payload)
        if r.status_code == 200:
            return True, "trade closed"
        return False, f"error {r.status_code}"
    except requests.RequestException as e:
        return False, f"network error: {e}"


def fetch_ltp(symbol: str) -> float | None:
    """Fetch latest traded price for a symbol from the API."""
    try:
        r = _get(f"/shared/ltp/{symbol.upper()}")
        if r.status_code == 200:
            return float(r.json()["price"])
        return None
    except requests.RequestException:
        return None


def start_accum_position(
    symbol: str, price: Decimal | float, qty: int
) -> tuple[bool, str]:
    payload = {"symbol": symbol, "price": str(price), "qty": qty}
    try:
        r = _post("/accumulation/positions", json=payload)
        if r.status_code == 201:
            return True, "position started"
        return False, f"error {r.status_code}: {r.text[:120]}"
    except requests.RequestException as e:
        return False, f"network error: {e}"


def log_tranche_fill(
    position_id: int, price: Decimal | float, qty: int
) -> tuple[bool, str]:
    payload = {"price": str(price), "qty": qty}
    try:
        r = _post(f"/accumulation/positions/{position_id}/tranches", json=payload)
        if r.status_code == 201:
            return True, "tranche logged"
        return False, f"error {r.status_code}: {r.text[:120]}"
    except requests.RequestException as e:
        return False, f"network error: {e}"


def exit_accum_position(
    position_id: int, price: Decimal | float, qty: int, reason: str = "manual"
) -> tuple[bool, str]:
    payload = {"price": str(price), "qty": qty, "reason": reason}
    try:
        r = _post(f"/accumulation/positions/{position_id}/exit", json=payload)
        if r.status_code == 200:
            return True, "position exited"
        return False, f"error {r.status_code}: {r.text[:120]}"
    except requests.RequestException as e:
        return False, f"network error: {e}"


def pause_position(position_id: int, reason: str) -> tuple[bool, str]:
    try:
        r = _post(f"/accumulation/positions/{position_id}/pause", json={"reason": reason})
        if r.status_code == 200:
            return True, "position paused"
        return False, f"error {r.status_code}"
    except requests.RequestException as e:
        return False, f"network error: {e}"


def resume_position(position_id: int) -> tuple[bool, str]:
    try:
        r = _post(f"/accumulation/positions/{position_id}/resume")
        if r.status_code == 200:
            return True, "position resumed"
        return False, f"error {r.status_code}"
    except requests.RequestException as e:
        return False, f"network error: {e}"


def fetch_chart_data(
    symbol: str, signal_id: int | None = None, days: int = 300
) -> dict | None:
    params: dict[str, str] = {"days": str(days)}
    if signal_id is not None:
        params["signal_id"] = str(signal_id)
    try:
        r = requests.get(
            f"{_base()}/shared/chart/{symbol}",
            headers=_headers(),
            params=params,
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
        return None
    except requests.RequestException:
        return None


def convert_to_swing(position_id: int) -> tuple[bool, str]:
    try:
        r = _post(f"/accumulation/positions/{position_id}/convert-to-swing")
        if r.status_code == 200:
            return True, "converted to swing"
        return False, f"error {r.status_code}"
    except requests.RequestException as e:
        return False, f"network error: {e}"


def fetch_portfolio_snapshot() -> dict | None:
    try:
        r = requests.get(
            f"{_base()}/shared/portfolio-snapshot",
            headers=_headers(),
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()
        return None
    except requests.RequestException:
        return None


def fetch_notifications(include_dismissed: bool = False) -> list[dict]:
    try:
        r = requests.get(
            f"{_base()}/shared/notifications",
            headers=_headers(),
            params={"include_dismissed": str(include_dismissed).lower()},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        return []
    except requests.RequestException:
        return []


def dismiss_notification(notification_id: int) -> bool:
    try:
        r = _post(f"/shared/notifications/{notification_id}/dismiss")
        return r.status_code == 200
    except requests.RequestException:
        return False


def trigger_price_check() -> dict | None:
    try:
        r = _post("/shared/portfolio-snapshot/check", timeout=30)
        if r.status_code == 200:
            return r.json()
        return None
    except requests.RequestException:
        return None
