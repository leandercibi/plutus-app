from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from plutus.config.settings import Settings
from plutus.db.models import AccumulationCandidate


@dataclass(frozen=True)
class TranchePlan:
    base_qty: int
    seed_price: Decimal
    n_tranches: int = 5


class TranchePlanner:
    """Spec 08 §5.1 — splits the position's pool budget into equal tranches.

    `seed_price` is supplied explicitly because AccumulationCandidate carries no
    price column; the caller passes the seed (initial entry) price.
    """

    def __init__(self, settings: Settings) -> None:
        self._n_tranches = settings.accumulation_n_tranches

    def make_plan(
        self,
        signal: AccumulationCandidate,
        pool_value: Decimal,
        seed_price: Decimal,
    ) -> TranchePlan:
        if seed_price <= 0:
            raise ValueError("seed_price must be positive")
        if self._n_tranches <= 0:
            raise ValueError("n_tranches must be positive")
        per_tranche_budget = pool_value / Decimal(self._n_tranches)
        base_qty = int(per_tranche_budget / seed_price)
        return TranchePlan(
            base_qty=base_qty,
            seed_price=seed_price,
            n_tranches=self._n_tranches,
        )
