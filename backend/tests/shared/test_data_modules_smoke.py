from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "plutus.shared.types",
        "plutus.shared.scoring_inputs",
        "plutus.shared.calibration.protocol",
        "plutus.db.init_db",
    ],
)
def test_pure_data_module_imports(module: str) -> None:
    """TESTING.md §2: pure-data / protocol modules get a smoke import test."""
    assert importlib.import_module(module) is not None
