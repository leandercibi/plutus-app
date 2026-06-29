from __future__ import annotations

from pathlib import Path

import pytest

_SMART_MONEY_DIR = (
    Path(__file__).parents[3] / "src" / "plutus" / "shared" / "smart_money"
)


@pytest.mark.hallmark
def test_no_fii_dii_in_per_stock() -> None:
    """A7/C1 hallmark: FII/DII relocated to shared/regime; per-stock smart money
    must not consume or reference FII/DII. Equivalent to the spec's
    `grep -r "fii|dii" src/plutus/shared/smart_money/` returning nothing.
    """
    offenders: list[str] = []
    for py in _SMART_MONEY_DIR.glob("*.py"):
        text = py.read_text().lower()
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "fii" in line or "dii" in line:
                offenders.append(f"{py.name}:{line_no}: {line.strip()}")
    assert offenders == [], f"FII/DII tokens found in smart_money: {offenders}"
