from __future__ import annotations

from plutus.config.settings import Settings
from plutus.shared.calibration.deadzone import is_in_soft_dead_zone


def test_dead_zone_bounds_inclusive() -> None:
    s = Settings(_env_file=None)  # 67..73
    assert is_in_soft_dead_zone(67, s) is True
    assert is_in_soft_dead_zone(70, s) is True
    assert is_in_soft_dead_zone(73, s) is True


def test_outside_dead_zone() -> None:
    s = Settings(_env_file=None)
    assert is_in_soft_dead_zone(66, s) is False
    assert is_in_soft_dead_zone(74, s) is False
