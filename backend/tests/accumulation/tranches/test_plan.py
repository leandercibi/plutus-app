from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from plutus.accumulation.tranches.plan import TranchePlanner
from plutus.config.settings import Settings
from plutus.db.models import AccumulationCandidate


def _candidate(symbol: str = "TCS") -> AccumulationCandidate:
    return AccumulationCandidate(
        run_id="r1",
        symbol=symbol,
        score=80,
        rs_30=0.05,
        rs_90=0.08,
        rs_180=0.10,
        cagr_eps_3y=0.15,
        valuation_pillar_pct=22.0,
        thesis_text="quality compounder",
        hard_avoid_active=False,
        created_at=datetime(2024, 1, 1),
    )


@pytest.fixture
def planner() -> TranchePlanner:
    return TranchePlanner(Settings(_env_file=None))


def test_five_tranches(planner: TranchePlanner) -> None:
    plan = planner.make_plan(_candidate(), pool_value=Decimal("1000000"), seed_price=Decimal("100"))
    assert plan.n_tranches == 5


def test_base_qty_sized_from_pool(planner: TranchePlanner) -> None:
    # pool 1,000,000 across 5 tranches at price 100 -> 200,000 per tranche / 100 = 2000 qty
    plan = planner.make_plan(_candidate(), pool_value=Decimal("1000000"), seed_price=Decimal("100"))
    assert plan.base_qty == 2000
    assert plan.seed_price == Decimal("100")


def test_base_qty_positive(planner: TranchePlanner) -> None:
    plan = planner.make_plan(_candidate(), pool_value=Decimal("500000"), seed_price=Decimal("250"))
    assert plan.base_qty > 0
