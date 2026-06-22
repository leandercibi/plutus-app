from __future__ import annotations

import pytest

from plutus.accumulation.fundamentals.hard_avoid import (
    FundamentalsSnapshot,
    HardAvoid,
)
from plutus.config.settings import Settings


def _snapshot(**overrides: object) -> FundamentalsSnapshot:
    base: dict[str, object] = {
        "de": 0.5,
        "is_financial": False,
        "last_eps_yoy_change": 0.10,
        "improving_guidance": False,
        "going_concern_flag": False,
        "promoter_pledge_increase_pp": 0.0,
        "roce": 0.20,
        "fcf_margin": 0.15,
        "pe_ttm": 18.0,
    }
    base.update(overrides)
    return FundamentalsSnapshot(**base)  # type: ignore[arg-type]


@pytest.fixture
def hard_avoid() -> HardAvoid:
    return HardAvoid(Settings(_env_file=None))


def test_clean_fundamentals_do_not_fire(hard_avoid: HardAvoid) -> None:
    result = hard_avoid.evaluate(_snapshot())
    assert result.avoid is False
    assert result.reasons == []


def test_de_breach_fires_for_non_financial(hard_avoid: HardAvoid) -> None:
    result = hard_avoid.evaluate(_snapshot(de=2.0, is_financial=False))
    assert result.avoid is True
    assert any("D/E" in r for r in result.reasons)


def test_de_breach_exempt_for_financial(hard_avoid: HardAvoid) -> None:
    result = hard_avoid.evaluate(_snapshot(de=2.0, is_financial=True))
    assert result.avoid is False


def test_eps_collapse_fires(hard_avoid: HardAvoid) -> None:
    result = hard_avoid.evaluate(
        _snapshot(last_eps_yoy_change=-0.60, improving_guidance=False)
    )
    assert result.avoid is True
    assert any("EPS" in r for r in result.reasons)


def test_eps_collapse_with_improving_guidance_does_not_fire(
    hard_avoid: HardAvoid,
) -> None:
    result = hard_avoid.evaluate(
        _snapshot(last_eps_yoy_change=-0.60, improving_guidance=True)
    )
    assert result.avoid is False


def test_going_concern_fires(hard_avoid: HardAvoid) -> None:
    result = hard_avoid.evaluate(_snapshot(going_concern_flag=True))
    assert result.avoid is True
    assert any("going concern" in r.lower() for r in result.reasons)


def test_promoter_pledge_increase_fires(hard_avoid: HardAvoid) -> None:
    result = hard_avoid.evaluate(_snapshot(promoter_pledge_increase_pp=12.0))
    assert result.avoid is True
    assert any("pledge" in r.lower() for r in result.reasons)


def test_multiple_reasons_accumulate(hard_avoid: HardAvoid) -> None:
    result = hard_avoid.evaluate(
        _snapshot(de=3.0, going_concern_flag=True, promoter_pledge_increase_pp=15.0)
    )
    assert result.avoid is True
    assert len(result.reasons) >= 3
