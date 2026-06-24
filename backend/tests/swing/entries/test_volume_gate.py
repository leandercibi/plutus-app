from __future__ import annotations

import pandas as pd
import pytest

from plutus.config.settings import Settings
from plutus.swing.entries.volume_gate import VolumeGate


@pytest.fixture
def gate() -> VolumeGate:
    return VolumeGate(Settings(_env_file=None))


def _delivery_frame(traded_qty: list[int], delivery_pct: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "traded_qty": traded_qty,
            "delivery_pct": delivery_pct,
        }
    )


def test_delivery_adjusted_volume_above_threshold_passes(gate: VolumeGate) -> None:
    # 20 baseline days of delivery-adjusted volume = 100_000 * 0.5 = 50_000.
    # confirmation candle: 200_000 * 0.5 = 100_000 = 2.0x median > 1.3x -> pass.
    traded = [100_000] * 20 + [200_000]
    delpct = [0.5] * 21
    delivery = _delivery_frame(traded, delpct)
    candles = pd.DataFrame({"close": [10.0] * 21})
    assert gate.passes(candles, delivery, today_idx=20) is True


def test_delivery_adjusted_volume_below_threshold_fails(gate: VolumeGate) -> None:
    # confirmation = 110_000 * 0.5 = 55_000 = 1.1x median < 1.3x -> fail.
    traded = [100_000] * 20 + [110_000]
    delpct = [0.5] * 21
    delivery = _delivery_frame(traded, delpct)
    candles = pd.DataFrame({"close": [10.0] * 21})
    assert gate.passes(candles, delivery, today_idx=20) is False


def test_expiry_day_skips_gate_returns_true(gate: VolumeGate) -> None:
    # Even with weak volume, an expiry day means the gate is NOT applied -> True.
    traded = [100_000] * 20 + [10_000]  # tiny volume that would otherwise fail
    delpct = [0.5] * 21
    delivery = _delivery_frame(traded, delpct)
    candles = pd.DataFrame({"close": [10.0] * 21})
    assert gate.passes(candles, delivery, today_idx=20, is_expiry_day=True) is True


def test_expiry_via_delivery_column(gate: VolumeGate) -> None:
    traded = [100_000] * 20 + [10_000]
    delpct = [0.5] * 21
    delivery = _delivery_frame(traded, delpct)
    delivery["is_expiry_or_rebalance_day"] = [False] * 20 + [True]
    candles = pd.DataFrame({"close": [10.0] * 21})
    assert gate.passes(candles, delivery, today_idx=20) is True


def test_threshold_uses_settings_multiplier() -> None:
    # exactly at 1.3x median should NOT pass (strictly greater required)
    settings = Settings(_env_file=None)
    gate = VolumeGate(settings)
    median_dav = 50_000.0
    confirmation_traded = int((median_dav * settings.volume_gate_delivery_mult) / 0.5)
    traded = [100_000] * 20 + [confirmation_traded]
    delpct = [0.5] * 21
    delivery = _delivery_frame(traded, delpct)
    candles = pd.DataFrame({"close": [10.0] * 21})
    # confirmation dav == 1.3x median exactly -> strictly-greater gate fails
    assert gate.passes(candles, delivery, today_idx=20) is False
