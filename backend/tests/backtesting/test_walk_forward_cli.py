from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from plutus.backtesting.walk_forward import WalkForwardReport, WFWindowResult, cli


def _report(overfit: bool = False) -> WalkForwardReport:
    return WalkForwardReport(
        symbol="RELIANCE",
        bundle="trend",
        windows=[
            WFWindowResult(is_sharpe=1.5, oos_sharpe=0.8, is_trades=6, oos_trades=3),
            WFWindowResult(is_sharpe=1.2, oos_sharpe=0.5, is_trades=5, oos_trades=2),
        ],
        is_sharpe_median=1.35,
        oos_sharpe_median=0.65,
        overfit_flag=overfit,
    )


def test_cli_smoke() -> None:
    with patch("plutus.backtesting.walk_forward.walk_forward", return_value=_report()):
        r = CliRunner().invoke(
            cli, ["--symbol", "RELIANCE", "--bundle", "trend", "--window", "30", "--step", "7"]
        )
    assert r.exit_code == 0, r.output
    assert "IS Sharpe median" in r.output


def test_cli_shows_oos_sharpe() -> None:
    with patch("plutus.backtesting.walk_forward.walk_forward", return_value=_report()):
        r = CliRunner().invoke(cli, ["--symbol", "RELIANCE", "--bundle", "trend"])
    assert "OOS Sharpe median" in r.output


def test_cli_shows_overfit_warning() -> None:
    with patch("plutus.backtesting.walk_forward.walk_forward", return_value=_report(overfit=True)):
        r = CliRunner().invoke(cli, ["--symbol", "RELIANCE", "--bundle", "trend"])
    assert "YES" in r.output


def test_cli_no_overfit_label_when_clean() -> None:
    with patch("plutus.backtesting.walk_forward.walk_forward", return_value=_report(overfit=False)):
        r = CliRunner().invoke(cli, ["--symbol", "RELIANCE", "--bundle", "trend"])
    assert r.exit_code == 0
    assert "no" in r.output.lower()
