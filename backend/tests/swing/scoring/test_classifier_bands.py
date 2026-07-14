from __future__ import annotations

import pytest

from plutus.config.settings import Settings
from plutus.swing.scoring.classifier import classify
from plutus.swing.scoring.expectancy import ExpectancyResult


def _exp(expectancy_R: float, *, primary: bool, fallback: bool = False) -> ExpectancyResult:
    return ExpectancyResult(
        expectancy_R=expectancy_R,
        p_t1=0.5,
        p_t2=0.2,
        p_sl=0.3,
        drawn_rr=2.0,
        passes_primary_gate=primary,
        passes_fallback_gate=fallback,
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


def test_score_70_is_buy_watch(settings: Settings) -> None:
    out = classify(70, _exp(0.5, primary=True), "high", settings)
    assert out.label == "BUY_WATCH"
    assert out.soft_dead_zone is True


def test_score_76_with_expectancy_pass_is_buy(settings: Settings) -> None:
    out = classify(76, _exp(0.5, primary=True), "high", settings)
    assert out.label == "BUY"


def test_score_65_is_watch(settings: Settings) -> None:
    out = classify(65, _exp(0.5, primary=True), "medium", settings)
    assert out.label == "WATCH"


def test_hard_kill_is_avoid(settings: Settings) -> None:
    out = classify(80, _exp(0.5, primary=True), "high", settings, hard_avoid=True)
    assert out.label == "AVOID"


def test_negative_expectancy_is_avoid(settings: Settings) -> None:
    out = classify(80, _exp(-0.1, primary=False), "high", settings)
    assert out.label == "AVOID"


def test_failing_both_gates_is_hold(settings: Settings) -> None:
    out = classify(80, _exp(0.1, primary=False, fallback=False), "low", settings)
    assert out.label == "HOLD"


def test_buy_watch_counterfactual_names_flip(settings: Settings) -> None:
    out = classify(70, _exp(0.5, primary=True), "high", settings)
    assert "BUY" in out.counterfactual
    assert "score" in out.counterfactual.lower()
