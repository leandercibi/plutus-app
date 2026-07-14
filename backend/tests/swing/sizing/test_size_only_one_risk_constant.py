from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from plutus.config.settings import Settings
from plutus.swing.sizing.size import PositionSizer

_SIZING_DIR = Path(__file__).parents[3] / "src" / "plutus" / "swing" / "sizing"


@pytest.fixture
def sizer() -> PositionSizer:
    return PositionSizer(Settings(_env_file=None))


def test_qty_from_risk_per_trade_at_default(sizer: PositionSizer) -> None:
    # pool 1,000,000 * 0.01 = 10,000 risk INR; risk/share = 5 -> 2000 shares
    # adv cap: 10,000,000 * 0.10 = 1,000,000 -> risk binds
    qty = sizer.compute_qty(
        entry=Decimal("100"),
        stop_loss=Decimal("95"),
        pool_value=Decimal("1000000"),
        adv_20d=10_000_000,
        governor_multiplier=1.0,
    )
    assert qty == 2000


def test_adv_cap_bites_for_large_position(sizer: PositionSizer) -> None:
    # tiny risk/share -> huge qty_by_risk, but ADV cap clips it
    qty = sizer.compute_qty(
        entry=Decimal("100"),
        stop_loss=Decimal("99.99"),
        pool_value=Decimal("1000000"),
        adv_20d=1000,
        governor_multiplier=1.0,
    )
    assert qty == 100  # 1000 * 0.10


def test_drawdown_governor_halves_qty(sizer: PositionSizer) -> None:
    full = sizer.compute_qty(Decimal("100"), Decimal("95"), Decimal("1000000"), 10_000_000, 1.0)
    halved = sizer.compute_qty(Decimal("100"), Decimal("95"), Decimal("1000000"), 10_000_000, 0.5)
    assert halved == full // 2


@pytest.mark.hallmark
def test_size_only_one_risk_constant() -> None:
    """A6 hallmark: no other constant in swing/sizing/ multiplies pool by 0.01-0.05.

    Only settings.risk_per_trade_pct controls per-trade risk. We AST-scan for any
    numeric literal in [0.01, 0.05] used as a multiplier.
    """
    offenders: list[str] = []
    for py in _SIZING_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, float)
                and 0.01 <= node.value <= 0.05
            ):
                offenders.append(f"{py.name}:{node.lineno} -> {node.value}")
    assert offenders == [], f"hardcoded risk constants found: {offenders}"
