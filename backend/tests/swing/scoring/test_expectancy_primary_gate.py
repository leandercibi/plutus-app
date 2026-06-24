from __future__ import annotations

from decimal import Decimal

import pytest

from plutus.config.settings import Settings
from plutus.shared.cost_model.costs import CostModel
from plutus.shared.scoring_inputs import ExpectancyInputs
from plutus.swing.scoring.expectancy import compute_expectancy
from tests.shared.calibration.stub import StubCalibration


@pytest.fixture
def costs() -> CostModel:
    return CostModel(Settings(_env_file=None))


def _inputs(bundle: str = "trend") -> ExpectancyInputs:
    # entry 100, stop 95 (risk 5), T1 110 (+2R gross), T2 120 (+4R gross)
    return ExpectancyInputs(
        bundle=bundle,
        regime="BULL",
        entry=Decimal("100"),
        stop_loss=Decimal("95"),
        target_1=Decimal("110"),
        target_2=Decimal("120"),
        qty=100,
    )


@pytest.mark.hallmark
def test_expectancy_is_primary_gate_when_calibration_sufficient(
    costs: CostModel,
) -> None:
    """A4: high-hit-rate setup passes via positive net expectancy."""
    calib = StubCalibration(
        rates={
            ("trend", "BULL", "target_1"): 0.60,
            ("trend", "BULL", "target_2"): 0.25,
            ("trend", "BULL", "stop"): 0.30,
        },
        n={("trend", "BULL"): 50},
    )
    res = compute_expectancy(_inputs(), calib, costs, settings=Settings(_env_file=None))
    assert res.passes_primary_gate
    assert res.expectancy_R > 0.3


@pytest.mark.hallmark
def test_low_hit_rate_high_drawn_rr_fails_primary_gate(costs: CostModel) -> None:
    """A4: a 2.2x drawn-RR setup with poor hit rate fails on negative net expectancy,
    even though drawn R:R looks attractive."""
    calib = StubCalibration(
        rates={
            ("trend", "BULL", "target_1"): 0.25,
            ("trend", "BULL", "target_2"): 0.05,
            ("trend", "BULL", "stop"): 0.70,
        },
        n={("trend", "BULL"): 50},
    )
    res = compute_expectancy(_inputs(), calib, costs, settings=Settings(_env_file=None))
    assert not res.passes_primary_gate
    assert res.expectancy_R < 0.3


def test_fallback_gate_used_when_sample_small(costs: CostModel) -> None:
    """A4: calibration n < 20 -> primary gate not authoritative; fallback drawn-RR floor applies."""
    calib = StubCalibration(n={("trend", "BULL"): 5})
    res = compute_expectancy(_inputs(), calib, costs, settings=Settings(_env_file=None))
    # drawn_rr = (T1-entry)/(entry-stop) = (110-100)/(100-95) = 2.0 >= 1.5 floor
    assert res.drawn_rr == pytest.approx(2.0)
    assert res.passes_fallback_gate


def test_costs_reduce_expectancy(costs: CostModel) -> None:
    """A4: enabling costs lowers net expectancy vs a zero-cost model."""

    class _ZeroCost(CostModel):
        def round_trip_cost(self, qty: int, entry: Decimal, exit: Decimal) -> Decimal:
            return Decimal("0")

    calib = StubCalibration(
        rates={
            ("trend", "BULL", "target_1"): 0.55,
            ("trend", "BULL", "target_2"): 0.20,
            ("trend", "BULL", "stop"): 0.40,
        },
        n={("trend", "BULL"): 50},
    )
    settings = Settings(_env_file=None)
    with_costs = compute_expectancy(_inputs(), calib, costs, settings=settings)
    no_costs = compute_expectancy(
        _inputs(), calib, _ZeroCost(settings), settings=settings
    )
    assert with_costs.expectancy_R < no_costs.expectancy_R
