from __future__ import annotations

from plutus.shared.smart_money.per_stock_score import PerStockFlow
from tests.shared.smart_money._flow_inputs import bb, delivery, mf


def test_total_capped_at_15_both_domains() -> None:
    for domain in ("swing", "accumulation"):
        out = PerStockFlow().compose(
            delivery(15),
            bb(15),
            mf("ACCUMULATING", 1.0),
            domain=domain,  # type: ignore[arg-type]
        )
        assert out.total_0_15 == 15
