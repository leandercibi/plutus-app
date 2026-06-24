from __future__ import annotations

from dataclasses import dataclass

from plutus.shared.benchmarks.strip import BenchmarkResult


@dataclass(frozen=True)
class CalibrationLine:
    bucket: str
    regime: str
    n: int
    win_rate: float
    expectancy_R: float
    ci_low_R: float
    ci_high_R: float


@dataclass(frozen=True)
class PostmortemInputs:
    week_ending: str
    benchmarks: BenchmarkResult
    calibration_lines: list[CalibrationLine]
    realized_expectancy_R: float
    forecast_expectancy_R: float
    slippage_divergence_bps: float | None
    wrong_direction_count: int


def build_postmortem_md(inputs: PostmortemInputs) -> str:
    """Spec 07 §12 — weekly markdown. C5: win rate is never the headline; the
    benchmark strip and expectancy lead. B2: all three baselines shown."""
    b = inputs.benchmarks
    lines: list[str] = []
    lines.append(f"# Weekly Postmortem — {inputs.week_ending}")
    lines.append("")
    lines.append("## Net vs benchmarks (B2)")
    lines.append(f"- Plutus: {b.plutus_net_pct:.2f}%")
    lines.append(f"- Nifty buy & hold: {b.nifty_net_pct:.2f}%")
    lines.append(f"- Regime-switched: {b.regime_switched_net_pct:.2f}%")
    lines.append(f"- Random liquid baseline: {b.random_liquid_net_pct:.2f}%")
    lines.append(
        f"- Profit factor: {b.plutus_profit_factor:.2f}  (n={b.plutus_n_trades})"
    )
    lines.append("")
    lines.append("## Expectancy")
    lines.append(f"- Realized expectancy: {inputs.realized_expectancy_R:.2f}R")
    lines.append(f"- Forecast expectancy: {inputs.forecast_expectancy_R:.2f}R")
    lines.append("")
    lines.append("## Bucket calibration (with CIs)")
    lines.append("| bucket | regime | n | win_rate | expectancy_R | CI |")
    lines.append("|---|---|---|---|---|---|")
    for c in inputs.calibration_lines:
        lines.append(
            f"| {c.bucket} | {c.regime} | {c.n} | {c.win_rate:.1%} | "
            f"{c.expectancy_R:.2f}R | [{c.ci_low_R:.2f}, {c.ci_high_R:.2f}] |"
        )
    lines.append("")
    lines.append("## Diagnostics")
    if inputs.slippage_divergence_bps is not None:
        lines.append(
            f"- Mock-vs-real slippage divergence: {inputs.slippage_divergence_bps:.1f} bps"
        )
    lines.append(f"- WRONG_DIRECTION count: {inputs.wrong_direction_count}")
    lines.append("")
    return "\n".join(lines)
