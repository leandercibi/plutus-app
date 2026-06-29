from __future__ import annotations

from decimal import Decimal

from plutus.config.settings import Settings
from plutus.shared.regime.detector import RegimeInputs
from plutus.swing.scoring.regime_pillar import regime_pillar_continuous


def _inputs(
    *,
    breadth: float = 0.50,
    vix: float = 20.0,
    fii_5d_inr: int = 0,
) -> RegimeInputs:
    return RegimeInputs(
        nifty_close=Decimal("20000"),
        nifty_50dma=Decimal("19500"),
        nifty_200dma=Decimal("18500"),
        pct_above_50dma=breadth,
        pct_above_200dma=breadth,
        advance_decline=1.0,
        india_vix=vix,
        fii_flow_5d_sum_inr=Decimal(fii_5d_inr),
        dii_flow_5d_sum_inr=Decimal(0),
        pct_above_50dma_5d_ago=breadth,
    )


def test_regime_pillar_is_bounded_0_to_15() -> None:
    settings = Settings(environment="test")
    for breadth in (0.0, 0.5, 1.0):
        for vix in (8.0, 18.0, 24.0, 40.0):
            for fii in (-10_000_000_000, 0, 10_000_000_000):
                out = regime_pillar_continuous(
                    _inputs(breadth=breadth, vix=vix, fii_5d_inr=fii), settings
                )
                assert 0 <= out.score <= 15


def test_full_bull_inputs_saturate_high() -> None:
    settings = Settings(environment="test")
    out = regime_pillar_continuous(
        _inputs(breadth=0.85, vix=10.0, fii_5d_inr=50_000_000_000_000),  # 50 lakh cr
        settings,
    )
    assert out.score >= 14


def test_full_bear_inputs_saturate_low() -> None:
    settings = Settings(environment="test")
    out = regime_pillar_continuous(
        _inputs(breadth=0.10, vix=30.0, fii_5d_inr=-50_000_000_000_000),
        settings,
    )
    assert out.score <= 1


def test_continuous_grading_within_sideways() -> None:
    """The legacy bucket lookup mapped every SIDEWAYS run to a flat 7. The
    continuous pillar must score an improving SIDEWAYS strictly higher than a
    deteriorating one.
    """
    settings = Settings(environment="test")
    improving = regime_pillar_continuous(
        _inputs(breadth=0.65, vix=16.0, fii_5d_inr=5_000_000_000), settings
    )
    deteriorating = regime_pillar_continuous(
        _inputs(breadth=0.35, vix=24.0, fii_5d_inr=-5_000_000_000), settings
    )
    assert improving.score > deteriorating.score


def test_breadth_drives_largest_share() -> None:
    """Breadth carries 7/15 of the pillar's budget by spec; isolated movement on
    breadth must move the score more than isolated movement on FII flow."""
    settings = Settings(environment="test")
    high_breadth = regime_pillar_continuous(_inputs(breadth=0.70), settings).score
    low_breadth = regime_pillar_continuous(_inputs(breadth=0.30), settings).score
    high_fii = regime_pillar_continuous(_inputs(fii_5d_inr=10_000_000_000), settings).score
    low_fii = regime_pillar_continuous(_inputs(fii_5d_inr=-10_000_000_000), settings).score
    assert (high_breadth - low_breadth) >= (high_fii - low_fii)
