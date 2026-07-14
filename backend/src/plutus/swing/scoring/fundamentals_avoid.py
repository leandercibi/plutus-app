from __future__ import annotations

from dataclasses import dataclass

from plutus.config.settings import Settings


@dataclass(frozen=True)
class FundamentalsAvoidResult:
    avoid: bool
    reason: str | None = None


def evaluate_fundamentals_avoid(
    de: float, is_financial: bool, settings: Settings
) -> FundamentalsAvoidResult:
    """Veto momentum trades on dangerously leveraged non-financial companies.

    A hard gate, separate from `fundamentals_score` below — balance-sheet risk can make a
    stock dangerous to hold at any horizon, so it vetoes the trade outright rather than
    just costing points. Mirrors accumulation's D/E hard-avoid check (financial-sector
    companies are exempt since leverage is structural to their business).
    """
    if not is_financial and de > settings.swing_de_max:
        return FundamentalsAvoidResult(
            avoid=True,
            reason=f"D/E {de:.2f} exceeds max {settings.swing_de_max:.2f} (non-financial)",
        )
    return FundamentalsAvoidResult(avoid=False)


# Absolute P/E band (not history-relative): yfinance doesn't expose a reliable 5-year
# median P/E (falls back to trailing P/E, which would always yield a zero discount), so
# unlike accumulation's valuation pillar this scores cheapness against a fixed band.
_PE_CHEAP = 15.0
_PE_EXPENSIVE = 40.0
_ROCE_FULL_POINTS_AT = 0.25  # 25% ROCE earns full points, same ceiling as accumulation


def fundamentals_score(roce: float, pe_ttm: float | None) -> int:
    """0-10 graded fundamentals score for swing signals: capital efficiency (ROCE, 0-5
    pts) + absolute valuation cheapness (trailing P/E, 0-5 pts).

    Deliberately excludes growth and history-relative valuation (accumulation's
    approach) — those need multi-year data that's either unreliable or absent from
    yfinance for this use case. pe_ttm=None (data unavailable) scores 0 for that half,
    never a fabricated number.
    """
    roce_pts = min(max(roce, 0.0) / _ROCE_FULL_POINTS_AT, 1.0) * 5.0
    if pe_ttm is not None and pe_ttm > 0:
        valuation_pts = min(max((_PE_EXPENSIVE - pe_ttm) / (_PE_EXPENSIVE - _PE_CHEAP), 0.0), 1.0) * 5.0
    else:
        valuation_pts = 0.0
    return int(round(roce_pts + valuation_pts))
