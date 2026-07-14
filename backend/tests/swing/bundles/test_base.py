from __future__ import annotations

import pandas as pd
import pytest

from plutus.swing.bundles.base import BaseBundle, BundleContext


def test_base_bundle_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseBundle()  # type: ignore[abstract]


def test_subclass_missing_fit_signal_cannot_instantiate() -> None:
    class Incomplete(BaseBundle):
        name = "incomplete"
        horizon_days = (1, 5)

        def required_inputs(self) -> set:
            return {"ohlcv"}

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_complete_subclass_constructs() -> None:
    class Complete(BaseBundle):
        name = "complete"
        horizon_days = (1, 5)

        def fit_signal(self, symbol, candles, ctx):  # type: ignore[no-untyped-def]
            return None

        def required_inputs(self) -> set:
            return {"ohlcv"}

    b = Complete()
    assert b.fit_signal("X", pd.DataFrame(), BundleContext(symbol="X", regime="BULL")) is None
    assert b.required_inputs() == {"ohlcv"}
