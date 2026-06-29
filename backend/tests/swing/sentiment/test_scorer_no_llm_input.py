from __future__ import annotations

import ast
from pathlib import Path

_SCORER = Path("src/plutus/swing/sentiment/scorer.py")
_CORROBORATION = Path("src/plutus/swing/sentiment/corroboration.py")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_scorer_does_not_import_color_or_llm() -> None:
    mods = _imported_modules(_SCORER)
    for m in mods:
        assert "color" not in m, f"scorer must not import color: {m}"
        assert not m.startswith("plutus.llm"), f"scorer must not import llm: {m}"
        assert ".llm" not in m, f"scorer must not import llm: {m}"


def test_corroboration_does_not_import_color_or_llm() -> None:
    mods = _imported_modules(_CORROBORATION)
    for m in mods:
        assert "color" not in m, f"corroboration must not import color: {m}"
        assert not m.startswith("plutus.llm"), f"corroboration must not import llm: {m}"
        assert ".llm" not in m, f"corroboration must not import llm: {m}"
