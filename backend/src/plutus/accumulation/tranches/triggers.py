from __future__ import annotations

from decimal import Decimal

# A13 — k_seq ATR-multiple schedule (spec 08 §5.2). The trigger drop for tranche
# `seq` is k_seq[seq] * atr_pct, NOT a fixed -8% / -15%.
_K_SEQ_SCHEDULE: dict[int, float] = {
    2: 1.5,
    3: 2.5,
    4: 3.5,
    5: 5.0,
}


class ATRNormalizedTrigger:
    """A13 — averaging-down trigger prices spaced by ATR multiples, not fixed %."""

    def next_trigger_price(
        self, last_filled_price: Decimal, atr_pct: float, tranche_seq: int
    ) -> Decimal:
        if tranche_seq not in _K_SEQ_SCHEDULE:
            raise ValueError(
                f"tranche_seq must be one of {sorted(_K_SEQ_SCHEDULE)}, got {tranche_seq}"
            )
        if atr_pct < 0.0:
            raise ValueError("atr_pct must be non-negative")
        k = _K_SEQ_SCHEDULE[tranche_seq]
        drop_fraction = Decimal(str(k * atr_pct))
        return last_filled_price * (Decimal("1") - drop_fraction)
