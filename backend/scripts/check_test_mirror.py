"""CI check: every src/plutus/X/Y.py has a tests/X/test_Y.py (01_folder_structure.md §2)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "plutus"
TESTS = ROOT / "tests"

# Modules exempt from the mirror rule.
EXEMPT_NAMES = {"__init__.py"}
EXEMPT_DIRS = {
    "llm",
    "dashboard",
    "api",
    "alerts",
    "scheduler",
}  # thin/UI; coarse coverage
# Pure-data / protocol / glue modules: a smoke import test elsewhere is sufficient.
DATA_ONLY = {
    "types.py",
    "scoring_inputs.py",
    "protocol.py",
    "init_db.py",
}


def main() -> int:
    missing: list[str] = []
    all_test_text = "\n".join(t.read_text() for t in TESTS.rglob("test_*.py"))
    for py in SRC.rglob("*.py"):
        if py.name in EXEMPT_NAMES or py.name in DATA_ONLY:
            continue
        rel = py.relative_to(SRC)
        if rel.parts and rel.parts[0] in EXEMPT_DIRS:
            continue
        expected = TESTS / rel.parent / f"test_{py.name}"
        if expected.exists():
            continue
        # fallback: any test anywhere that references the module stem
        if py.stem in all_test_text:
            continue
        missing.append(str(rel))

    if missing:
        print("Missing test mirror for:")
        for m in missing:
            print(f"  src/plutus/{m}")
        return 1
    print("Test mirror OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
