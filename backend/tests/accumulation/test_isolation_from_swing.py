from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ACCUMULATION_ROOT = Path(__file__).resolve().parents[2] / "src" / "plutus" / "accumulation"


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            modules.add(node.module)
    return modules


@pytest.mark.hallmark
def test_accumulation_does_not_import_swing() -> None:
    """Architectural isolation: accumulation/ must NEVER import from swing/.

    Cross-domain logic belongs in shared/. The only sanctioned cross-domain path is
    the voluntary bull-ready conversion, which uses an opaque `technicals` object —
    never the swing signal type.
    """
    offenders: list[str] = []
    for py_file in _ACCUMULATION_ROOT.rglob("*.py"):
        modules = _imported_modules(py_file.read_text())
        for module in modules:
            if module == "plutus.swing" or module.startswith("plutus.swing."):
                offenders.append(f"{py_file.name} imports {module}")
    assert offenders == [], f"accumulation imports swing: {offenders}"
