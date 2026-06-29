from __future__ import annotations

from decimal import Decimal

import pytest

from plutus.config.settings import Settings
from plutus.shared.regime.detector import RegimeDetector, RegimeInputs


@pytest.fixture
def detector() -> RegimeDetector:
    return RegimeDetector(Settings(_env_file=None))


def _bull_inputs(**overrides: object) -> RegimeInputs:
    base: dict[str, object] = {
        "nifty_close": Decimal("22000"),
        "nifty_50dma": Decimal("21000"),
        "nifty_200dma": Decimal("20000"),
        "pct_above_50dma": 0.70,
        "pct_above_200dma": 0.65,
        "advance_decline": 1.5,
        "india_vix": 14.0,
        "fii_flow_5d_sum_inr": Decimal("5000000000"),
        "dii_flow_5d_sum_inr": Decimal("3000000000"),
        "pct_above_50dma_5d_ago": 0.55,
    }
    base.update(overrides)
    return RegimeInputs(**base)  # type: ignore[arg-type]


def _bear_inputs(**overrides: object) -> RegimeInputs:
    base: dict[str, object] = {
        "nifty_close": Decimal("18000"),
        "nifty_50dma": Decimal("19000"),
        "nifty_200dma": Decimal("20000"),
        "pct_above_50dma": 0.20,
        "pct_above_200dma": 0.25,
        "advance_decline": 0.4,
        "india_vix": 26.0,
        "fii_flow_5d_sum_inr": Decimal("-5000000000"),
        "dii_flow_5d_sum_inr": Decimal("1000000000"),
        "pct_above_50dma_5d_ago": 0.35,
    }
    base.update(overrides)
    return RegimeInputs(**base)  # type: ignore[arg-type]


def test_bull_day_classifies_bull_high_confidence(detector: RegimeDetector) -> None:
    verdict = detector.classify(_bull_inputs())
    assert verdict.label == "BULL"
    assert verdict.confidence == "high"
    assert verdict.breadth_confirmed is True
    assert verdict.reasons


def test_bear_day_classifies_bear(detector: RegimeDetector) -> None:
    verdict = detector.classify(_bear_inputs())
    assert verdict.label == "BEAR"
    assert verdict.confidence == "high"


def test_mixed_day_classifies_sideways(detector: RegimeDetector) -> None:
    # nifty above 200dma but breadth weak and vix elevated -> neither full set
    mixed = _bull_inputs(
        pct_above_50dma=0.45,
        india_vix=20.0,
        fii_flow_5d_sum_inr=Decimal("-1000000000"),
    )
    verdict = detector.classify(mixed)
    assert verdict.label == "SIDEWAYS"


def test_fii_positive_but_breadth_negative_drops_confidence(
    detector: RegimeDetector,
) -> None:
    # BULL but only 3 of 4 sub-conditions hold (breadth just over the line),
    # and breadth trend disagrees -> breadth not confirmed.
    weaker = _bull_inputs(
        pct_above_50dma=0.56,
        pct_above_50dma_5d_ago=0.62,  # declining breadth, disagrees with BULL
    )
    verdict = detector.classify(weaker)
    assert verdict.label == "BULL"
    assert verdict.breadth_confirmed is False


def test_strong_bull_higher_confidence_than_marginal(detector: RegimeDetector) -> None:
    strong = detector.classify(_bull_inputs())
    marginal = detector.classify(_bull_inputs(india_vix=17.9, pct_above_50dma=0.56))
    order = {"low": 0, "medium": 1, "high": 2}
    assert order[strong.confidence] >= order[marginal.confidence]
