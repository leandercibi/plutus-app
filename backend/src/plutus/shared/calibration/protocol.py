from __future__ import annotations

from typing import Literal, Protocol

HitField = Literal["target_1", "target_2", "stop"]


class CalibrationLookup(Protocol):
    """Read path consumed by expectancy (A4) and composite_geometry (A5).

    The full DB-backed implementation lives in shared/calibration/lookup.py (Phase 2).
    Consumers depend only on this protocol so the A3 no-leak rule stays enforceable.
    """

    def hit_rate(self, bundle: str, regime: str, target_field: HitField) -> float: ...

    def confidence_band(
        self, bundle: str, regime: str, score_bucket: str
    ) -> Literal["low", "medium", "high"]: ...

    def n_for(self, bundle: str, regime: str) -> int: ...
