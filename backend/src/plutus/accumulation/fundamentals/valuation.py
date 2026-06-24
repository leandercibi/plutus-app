from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# A12 — Valuation pillar is hard-capped at 30 of 100. Growth pillar is out of 25.
VALUATION_MAX = 30
GROWTH_MAX = 25

# Internal sub-weights for the valuation score (sum == VALUATION_MAX).
_CHEAPNESS_MAX = 18  # PE discount vs 5y median
_GROWTH_QUALITY_MAX = 12  # only rewarded when earnings are actually growing


@dataclass(frozen=True)
class ValuationInputs:
    pe_ttm: float
    pe_5y_median: float
    ev_ebitda: float
    earnings_history_5y: pd.DataFrame  # columns: year, eps


class Valuation:
    """A12 — multi-year normalized earnings, CAGR-based growth, hard valuation cap."""

    def normalized_eps(self, history: pd.DataFrame) -> float:
        """Average EPS over the available fiscal years, excluding negative-EPS years."""
        positives = history.loc[history["eps"] >= 0.0, "eps"]
        if positives.empty:
            return 0.0
        return float(positives.mean())

    def cagr_eps(self, history: pd.DataFrame, years: int = 5) -> float | None:
        """CAGR across `years` of EPS history; None on negative endpoints or thin data."""
        ordered = history.sort_values("year")
        if len(ordered) < years:
            return None
        window = ordered.tail(years)
        start = float(window["eps"].iloc[0])
        end = float(window["eps"].iloc[-1])
        if start <= 0.0 or end <= 0.0:
            return None
        intervals = len(window) - 1
        if intervals <= 0:
            return None
        return float((end / start) ** (1.0 / intervals) - 1.0)

    def score(self, inputs: ValuationInputs) -> int:
        """Out of VALUATION_MAX (hard-capped). Cheap *and* growing scores high;
        cheap because cyclically declining (value trap) scores low."""
        cheapness = self._cheapness_points(inputs.pe_ttm, inputs.pe_5y_median)

        cagr = self.cagr_eps(inputs.earnings_history_5y, years=5)
        if cagr is None or cagr <= 0.0:
            # value trap: cheapness is discounted hard, no growth-quality credit
            trap_points = int(round(cheapness * 0.4))
            return _clamp(trap_points, VALUATION_MAX)

        growth_quality = _scaled_points(cagr, ceiling=0.20, max_points=_GROWTH_QUALITY_MAX)
        return _clamp(int(round(cheapness + growth_quality)), VALUATION_MAX)

    def growth_score(self, history: pd.DataFrame) -> int:
        """Out of GROWTH_MAX. Uses 3y and 5y CAGR (A12), never latest YoY.

        A base-effect spike (most of the multi-year gain concentrated in one YoY
        jump) is penalized via a consistency factor so it cannot max the score the
        way a steady compounder does.
        """
        cagr_3y = self.cagr_eps(history, years=4)  # 4 points => 3 intervals
        cagr_5y = self.cagr_eps(history, years=5)

        components: list[float] = []
        if cagr_3y is not None:
            components.append(cagr_3y)
        if cagr_5y is not None:
            components.append(cagr_5y)
        if not components:
            return 0
        blended_cagr = sum(components) / len(components)
        if blended_cagr <= 0.0:
            return 0
        raw = _scaled_points(blended_cagr, ceiling=0.25, max_points=GROWTH_MAX)
        consistency = self._growth_consistency(history)
        return int(round(raw * consistency))

    def _growth_consistency(self, history: pd.DataFrame) -> float:
        """Fraction in [0, 1]: how evenly multi-year EPS gains are distributed.

        Computed as 1 minus the concentration (max single-year share) of the total
        positive EPS gain. A steady compounder spreads gains across years (low
        concentration -> high consistency). A base-effect series whose gain is
        dominated by one spike year has high concentration -> low consistency,
        damping its growth points so a +120% YoY recovery cannot max the score.
        """
        ordered = history.sort_values("year")
        eps = ordered["eps"].to_numpy(dtype=float)
        if len(eps) < 2:
            return 0.0
        yoy_changes = eps[1:] - eps[:-1]
        positive_gains = yoy_changes[yoy_changes > 0.0]
        total_gain = float(positive_gains.sum())
        if total_gain <= 0.0:
            return 0.0
        max_share = float(positive_gains.max()) / total_gain
        return 1.0 - max_share

    def _cheapness_points(self, pe_ttm: float, pe_5y_median: float) -> float:
        if pe_ttm <= 0.0 or pe_5y_median <= 0.0:
            return 0.0
        discount = (pe_5y_median - pe_ttm) / pe_5y_median  # >0 means cheaper than history
        if discount <= 0.0:
            return 0.0
        return min(discount, 1.0) * _CHEAPNESS_MAX


def _scaled_points(value: float, ceiling: float, max_points: int) -> int:
    fraction = min(max(value, 0.0) / ceiling, 1.0)
    return int(round(fraction * max_points))


def _clamp(points: int, ceiling: int) -> int:
    return max(0, min(points, ceiling))
