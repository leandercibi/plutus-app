from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from plutus.config.settings import Settings
from plutus.swing.entries.circuit_gate import CircuitGate, CircuitStatus


@pytest.fixture
def gate() -> CircuitGate:
    return CircuitGate(Settings(_env_file=None))


def _candles(n: int, start: date = date(2025, 1, 1)) -> pd.DataFrame:
    days = pd.date_range(start, periods=n, freq="D")
    close = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame(
        {
            "date": days,
            "open": close,
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
        }
    )


def test_no_circuit_hits_no_suppression(gate: CircuitGate) -> None:
    candles = _candles(90)
    status = gate.status("INFY", candles, lookback_sessions=90)
    assert isinstance(status, CircuitStatus)
    assert status.hit_count == 0
    assert status.last_hit_date is None
    assert status.suppress is False


def test_one_limit_hit_30_days_ago_recommends_suppression(gate: CircuitGate) -> None:
    candles = _candles(90)
    # 30 sessions before the last bar (index 89) -> index 59, make it a locked-limit bar:
    # high == low (fully locked) and a >= circuit_pct move from prior close.
    hit_idx = 59
    prior_close = candles.loc[hit_idx - 1, "close"]
    locked_price = round(prior_close * 1.20, 2)  # +20% limit move, locked
    candles.loc[hit_idx, ["open", "high", "low", "close"]] = locked_price
    status = gate.status("INFY", candles, lookback_sessions=90)
    assert status.hit_count >= 1
    assert status.last_hit_date == candles.loc[hit_idx, "date"].date()
    assert status.suppress is True


def test_hit_outside_lookback_is_ignored(gate: CircuitGate) -> None:
    candles = _candles(200)
    # a circuit hit far in the past (index 5), outside a 90-session lookback
    prior_close = candles.loc[4, "close"]
    locked_price = round(prior_close * 1.20, 2)
    candles.loc[5, ["open", "high", "low", "close"]] = locked_price
    status = gate.status("INFY", candles, lookback_sessions=90)
    assert status.hit_count == 0
    assert status.suppress is False


def test_circuit_pct_is_configurable() -> None:
    # a 6% move counts as a circuit hit when circuit_pct=0.05
    gate = CircuitGate(Settings(_env_file=None), circuit_pct=0.05)
    candles = _candles(90)
    hit_idx = 70
    prior_close = candles.loc[hit_idx - 1, "close"]
    moved = round(prior_close * 1.06, 2)
    candles.loc[hit_idx, ["open", "high", "low", "close"]] = moved
    status = gate.status("INFY", candles, lookback_sessions=90)
    assert status.hit_count >= 1
