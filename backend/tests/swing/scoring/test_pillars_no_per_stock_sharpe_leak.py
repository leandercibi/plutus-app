from __future__ import annotations

import ast
from pathlib import Path

import pytest

_PILLARS_SRC = Path(__file__).parents[3] / "src" / "plutus" / "swing" / "scoring" / "pillars.py"


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
def test_pillars_no_per_stock_sharpe_leak() -> None:
    """A3 hallmark: the Technical pillar consumes raw price/momentum features only.

    It MUST NOT import BundleStatPerRegime, the per-regime store, or the selector,
    which would re-introduce the per-stock Sharpe circularity the review flagged.
    """
    joined = _imported_names(_PILLARS_SRC)
    assert "BundleStatPerRegime" not in joined
    assert "per_regime" not in joined
    assert "selector" not in joined
    assert "bundle_stat" not in joined.lower()
