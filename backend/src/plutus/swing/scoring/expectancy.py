from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from plutus.config.settings import Settings
from plutus.shared.calibration.protocol import CalibrationLookup
from plutus.shared.cost_model.costs import CostModel
from plutus.shared.scoring_inputs import ExpectancyInputs


@dataclass(frozen=True)
class ExpectancyResult:
    expectancy_R: float
    p_t1: float
    p_t2: float
    p_sl: float
    drawn_rr: float
    passes_primary_gate: bool
    passes_fallback_gate: bool


def _r_after_cost(
    move: Decimal,
    risk_per_share: Decimal,
    qty: int,
    exit_price: Decimal,
    entry: Decimal,
    costs: CostModel,
) -> float:
    gross_r = move / risk_per_share
    cost = costs.round_trip_cost(qty, entry, exit_price)
    cost_r = cost / (risk_per_share * Decimal(qty))
    return float(gross_r - cost_r)


def compute_expectancy(
    inputs: ExpectancyInputs,
    calibration: CalibrationLookup,
    costs: CostModel,
    settings: Settings,
) -> ExpectancyResult:
    """A4 — net probability-weighted expectancy after round-trip costs.

    E = p_t1 * R_t1 + p_t2 * R_t2 - p_sl * R_sl, R values net of costs.
    Hit rates conditioned on (bundle, regime). Floor: settings.expectancy_floor_R.
    Fallback: drawn_rr >= settings.drawn_rr_fallback_floor when calibration n < min.
    """
    risk_per_share = inputs.entry - inputs.stop_loss

    p_t1 = calibration.hit_rate(inputs.bundle, inputs.regime, "target_1")
    p_t2 = calibration.hit_rate(inputs.bundle, inputs.regime, "target_2")
    p_sl = calibration.hit_rate(inputs.bundle, inputs.regime, "stop")

    r_t1 = _r_after_cost(
        inputs.target_1 - inputs.entry,
        risk_per_share,
        inputs.qty,
        inputs.target_1,
        inputs.entry,
        costs,
    )
    r_t2 = _r_after_cost(
        inputs.target_2 - inputs.entry,
        risk_per_share,
        inputs.qty,
        inputs.target_2,
        inputs.entry,
        costs,
    )
    r_sl = _r_after_cost(
        inputs.entry - inputs.stop_loss,
        risk_per_share,
        inputs.qty,
        inputs.stop_loss,
        inputs.entry,
        costs,
    )

    expectancy_r = p_t1 * r_t1 + p_t2 * r_t2 - p_sl * r_sl
    drawn_rr = float((inputs.target_1 - inputs.entry) / risk_per_share)

    n = calibration.n_for(inputs.bundle, inputs.regime)
    sample_sufficient = n >= settings.calibration_min_n_low

    passes_primary = sample_sufficient and expectancy_r >= settings.expectancy_floor_R
    passes_fallback = (
        not sample_sufficient
    ) and drawn_rr >= settings.drawn_rr_fallback_floor

    return ExpectancyResult(
        expectancy_R=expectancy_r,
        p_t1=p_t1,
        p_t2=p_t2,
        p_sl=p_sl,
        drawn_rr=drawn_rr,
        passes_primary_gate=passes_primary,
        passes_fallback_gate=passes_fallback,
    )
