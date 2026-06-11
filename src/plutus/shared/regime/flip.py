from __future__ import annotations

from plutus.shared.regime.detector import RegimeVerdict


class RegimeFlipDetector:
    def is_flip(self, prior: RegimeVerdict, current: RegimeVerdict) -> bool:
        return prior.label != current.label and current.breadth_confirmed
