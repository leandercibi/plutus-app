from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from plutus.shared.calibration.protocol import HitField


@dataclass(frozen=True)
class StubCalibration:
    """In-test calibration lookup. Maps (bundle, regime, field) -> hit rate."""

    rates: dict[tuple[str, str, HitField], float] = field(default_factory=dict)
    n: dict[tuple[str, str], int] = field(default_factory=dict)
    pooled: dict[tuple[str, HitField], float] = field(default_factory=dict)
    min_n_low: int = 20

    def hit_rate(self, bundle: str, regime: str, target_field: HitField) -> float:
        if (
            self.n_for(bundle, regime) < self.min_n_low
            and (bundle, target_field) in self.pooled
        ):
            return self.pooled[(bundle, target_field)]
        return self.rates.get((bundle, regime, target_field), 0.0)

    def confidence_band(
        self, bundle: str, regime: str, score_bucket: str
    ) -> Literal["low", "medium", "high"]:
        nn = self.n_for(bundle, regime)
        if nn < 20:
            return "low"
        if nn < 50:
            return "medium"
        return "high"

    def n_for(self, bundle: str, regime: str) -> int:
        return self.n.get((bundle, regime), 0)
