from __future__ import annotations

import pytest

from plutus.shared.calibration.ci import bootstrap_R_interval, wilson_interval


def test_wilson_interval_known_value() -> None:
    # 8 successes of 10, 95% Wilson ~ (0.490, 0.943) per textbook
    lo, hi = wilson_interval(8, 10, 0.95)
    assert lo == pytest.approx(0.490, abs=0.01)
    assert hi == pytest.approx(0.943, abs=0.01)


def test_wilson_zero_n_is_zero_zero() -> None:
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_wilson_brackets_point_estimate() -> None:
    lo, hi = wilson_interval(50, 100, 0.95)
    assert lo < 0.5 < hi


def test_bootstrap_seeded_deterministic() -> None:
    rs = [1.0, -1.0, 0.5, 2.0, -0.5, 1.5]
    a = bootstrap_R_interval(rs, seed=42)
    b = bootstrap_R_interval(rs, seed=42)
    assert a == b


def test_bootstrap_empty_is_zero() -> None:
    assert bootstrap_R_interval([]) == (0.0, 0.0)


def test_bootstrap_brackets_mean() -> None:
    rs = [1.0, 1.0, 1.0, 1.0, 1.0]
    lo, hi = bootstrap_R_interval(rs, seed=1)
    assert lo == pytest.approx(1.0)
    assert hi == pytest.approx(1.0)
