from __future__ import annotations

from plutus.backtesting.walk_forward import WalkForwardReport, WFWindowResult


def _windows(pairs: list[tuple[float, float]]) -> list[WFWindowResult]:
    return [
        WFWindowResult(is_sharpe=is_, oos_sharpe=oos, is_trades=5, oos_trades=3)
        for is_, oos in pairs
    ]


def _overfit_ratio(windows: list[WFWindowResult]) -> float:
    n = sum(
        1 for w in windows if w.is_sharpe > 0 and (w.is_sharpe - w.oos_sharpe) / w.is_sharpe > 0.5
    )
    return n / len(windows) if windows else 0.0


def test_overfit_flag_when_oos_drops_more_than_50pct() -> None:
    # IS=2.0, OOS=0.5 → drop = (2.0-0.5)/2.0 = 75 % > 50 %
    windows = _windows([(2.0, 0.5), (1.5, 0.4), (1.0, 0.3)])
    assert _overfit_ratio(windows) >= 0.5


def test_no_overfit_when_oos_close_to_is() -> None:
    windows = _windows([(1.0, 0.9), (1.2, 1.1), (0.8, 0.8)])
    assert _overfit_ratio(windows) < 0.5


def test_negative_is_sharpe_not_counted_as_overfit() -> None:
    # IS is negative → formula undefined; rule only applies when IS > 0
    windows = _windows([(-0.5, -1.0), (-0.3, -0.8)])
    assert _overfit_ratio(windows) == 0.0


def test_walk_forward_report_fields() -> None:
    report = WalkForwardReport(
        symbol="RELIANCE",
        bundle="trend",
        windows=_windows([(1.8, 0.7)]),
        is_sharpe_median=1.8,
        oos_sharpe_median=0.7,
        overfit_flag=True,
    )
    assert report.symbol == "RELIANCE"
    assert report.overfit_flag is True
    assert len(report.windows) == 1


def test_walk_forward_run_model_exists() -> None:
    from datetime import datetime

    from plutus.db.models import WalkForwardRun

    row = WalkForwardRun(
        symbol="RELIANCE",
        bundle="trend",
        window_days=30,
        step_days=7,
        is_sharpe_median=1.8,
        oos_sharpe_median=0.7,
        overfit_flag=True,
        windows_json=[{"is_sharpe": 1.8, "oos_sharpe": 0.7}],
        created_at=datetime(2025, 1, 1),
    )
    assert row.symbol == "RELIANCE"
    assert row.overfit_flag is True
