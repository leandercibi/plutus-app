from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from plutus.shared.types import BundleSignal
from plutus.swing.scoring.composite_geometry import (
    probability_weighted_target,
    widest_stop,
)
from tests.shared.calibration.stub import StubCalibration


def _sig(bundle: str, stop: str, t1: str, t2: str) -> BundleSignal:
    return BundleSignal(
        symbol="INFY",
        bundle=bundle,
        as_of=date(2025, 1, 1),
        entry=Decimal("100"),
        stop_loss=Decimal(stop),
        target_1=Decimal(t1),
        target_2=Decimal(t2),
    )


def test_widest_stop_of_two_is_the_wider() -> None:
    a = _sig("trend", "97", "104", "108")
    b = _sig("breakout", "88", "124", "130")
    # for a long, wider stop = lower price = more risk
    assert widest_stop([a, b]) == Decimal("88")


def test_widest_stop_of_three_is_median() -> None:
    a = _sig("trend", "97", "104", "108")
    b = _sig("breakout", "88", "124", "130")
    c = _sig("vcp", "92", "115", "121")
    # stops sorted: 88, 92, 97 -> median 92
    assert widest_stop([a, b, c]) == Decimal("92")


def test_probability_weighted_target_matches_manual() -> None:
    a = _sig("trend", "97", "104", "108")
    b = _sig("breakout", "88", "124", "130")
    calib = StubCalibration(
        rates={
            ("trend", "BULL", "target_1"): 0.2,
            ("breakout", "BULL", "target_1"): 0.8,
        }
    )
    pwt = probability_weighted_target([a, b], "target_1", calib, "BULL")
    assert pwt == pytest.approx(Decimal("120"))


@pytest.mark.hallmark
def test_composite_a5_hallmark() -> None:
    """A5: composite must prefer widest-stop + probability-weighted-target geometry,
    yielding 1.67R, NOT the misleading tightest-stop + nearest-target 1.33R."""
    entry = Decimal("100")
    a = _sig("trend", "97", "104", "108")
    b = _sig("breakout", "88", "124", "130")
    calib = StubCalibration(
        rates={
            ("trend", "BULL", "target_1"): 0.2,
            ("breakout", "BULL", "target_1"): 0.8,
        }
    )

    composite_stop = widest_stop([a, b])
    composite_t1 = probability_weighted_target([a, b], "target_1", calib, "BULL")
    composite_r = float((composite_t1 - entry) / (entry - composite_stop))

    # the misleading variant
    tightest_stop = max(a.stop_loss, b.stop_loss)  # 97 -> least risk
    nearest_target = min(a.target_1, b.target_1)  # 104
    misleading_r = float((nearest_target - entry) / (entry - tightest_stop))

    assert composite_r == pytest.approx(1.6667, abs=1e-3)
    assert misleading_r == pytest.approx(1.3333, abs=1e-3)
    assert composite_r > misleading_r
