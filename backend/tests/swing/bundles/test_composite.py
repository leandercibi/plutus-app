from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from plutus.shared.types import BundleSignal
from plutus.swing.bundles.composite import CompositeBundle
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


def _calib() -> StubCalibration:
    return StubCalibration(
        rates={
            ("trend", "BULL", "target_1"): 0.2,
            ("breakout", "BULL", "target_1"): 0.8,
            ("vcp", "BULL", "target_1"): 0.5,
            ("trend", "BULL", "target_2"): 0.2,
            ("breakout", "BULL", "target_2"): 0.8,
            ("vcp", "BULL", "target_2"): 0.5,
        }
    )


def test_two_agreeing_sub_bundles_stop_is_widest() -> None:
    a = _sig("trend", "97", "104", "108")
    b = _sig("breakout", "88", "124", "130")
    composite = CompositeBundle(calibration=_calib(), regime="BULL")
    signal = composite.combine([a, b])
    assert signal is not None
    assert signal.bundle == "composite"
    # widest (lowest) stop wins
    assert signal.stop_loss == Decimal("88")


def test_one_sub_bundle_returns_none() -> None:
    a = _sig("trend", "97", "104", "108")
    composite = CompositeBundle(calibration=_calib(), regime="BULL")
    assert composite.combine([a]) is None


def test_three_sub_bundles_stop_is_median() -> None:
    a = _sig("trend", "97", "104", "108")
    b = _sig("breakout", "88", "124", "130")
    c = _sig("vcp", "92", "115", "121")
    composite = CompositeBundle(calibration=_calib(), regime="BULL")
    signal = composite.combine([a, b, c])
    assert signal is not None
    # stops 88, 92, 97 -> median 92
    assert signal.stop_loss == Decimal("92")


def test_probability_weighted_target_matches_manual() -> None:
    a = _sig("trend", "97", "104", "108")
    b = _sig("breakout", "88", "124", "130")
    composite = CompositeBundle(calibration=_calib(), regime="BULL")
    signal = composite.combine([a, b])
    assert signal is not None
    # weights 0.2 / 0.8 -> (0.2*104 + 0.8*124) = 120
    assert signal.target_1 == pytest.approx(Decimal("120"))


def test_fit_signal_uses_sub_signals_from_ctx() -> None:
    import pandas as pd

    from plutus.swing.bundles.base import BundleContext

    a = _sig("trend", "97", "104", "108")
    b = _sig("breakout", "88", "124", "130")
    composite = CompositeBundle(calibration=_calib(), regime="BULL")
    ctx = BundleContext(symbol="INFY", regime="BULL", extras={"sub_signals": [a, b]})
    signal = composite.fit_signal("INFY", pd.DataFrame(), ctx)
    assert signal is not None
    assert signal.stop_loss == Decimal("88")
    assert composite.required_inputs() == {"ohlcv", "delivery"}


def test_fit_signal_without_sub_signals_returns_none() -> None:
    import pandas as pd

    from plutus.swing.bundles.base import BundleContext

    composite = CompositeBundle(calibration=_calib(), regime="BULL")
    ctx = BundleContext(symbol="INFY", regime="BULL")
    assert composite.fit_signal("INFY", pd.DataFrame(), ctx) is None
