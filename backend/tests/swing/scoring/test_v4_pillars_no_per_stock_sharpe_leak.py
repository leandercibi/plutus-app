"""A3 leak rule extended to the v4 selection-brain pillars.

The original pillars.py is held to this rule by ``test_pillars_no_per_stock_sharpe_leak``.
This sibling test applies the same rule to the new pillar modules (rs_pillar,
flow_pillar, regime_pillar, composite_v4). If a future change pulls
BundleStatPerRegime / the per-regime store / the selector into any of them, the
per-stock Sharpe circularity comes back through a side door.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SCORING_DIR = (
    Path(__file__).parents[3] / "src" / "plutus" / "swing" / "scoring"
)
_GUARDED_FILES = (
    "rs_pillar.py",
    "flow_pillar.py",
    "regime_pillar.py",
    "composite_v4.py",
)


def _imported_names(path: Path) -> str:
    tree = ast.parse(path.read_text())
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return " ".join(names)


@pytest.mark.hallmark
@pytest.mark.parametrize("filename", _GUARDED_FILES)
def test_v4_pillars_no_per_stock_sharpe_leak(filename: str) -> None:
    path = _SCORING_DIR / filename
    assert path.exists(), f"expected {path} to exist"
    joined = _imported_names(path)
    assert "BundleStatPerRegime" not in joined
    assert "per_regime" not in joined
    assert "selector" not in joined
    assert "bundle_stat" not in joined.lower()
