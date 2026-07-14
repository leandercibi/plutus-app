from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from plutus.shared.types import BundleSignal
from plutus.swing.scoring.selector import (
    BundleRegimeStat,
    BundleSelector,
    SelectorInputs,
)


def _sig(bundle: str) -> BundleSignal:
    return BundleSignal(
        symbol="INFY",
        bundle=bundle,
        as_of=date(2025, 1, 1),
        entry=Decimal("100"),
        stop_loss=Decimal("95"),
        target_1=Decimal("110"),
        target_2=Decimal("120"),
    )


def _stat(bundle: str, regime: str, sharpe: float, n: int = 50) -> BundleRegimeStat:
    return BundleRegimeStat(bundle=bundle, regime=regime, oos_sharpe_shrunk=sharpe, n_trades=n)


def test_ranks_by_oos_per_regime_shrunk_sharpe() -> None:
    stats = {
        ("trend", "BULL"): _stat("trend", "BULL", 1.5),
        ("breakout", "BULL"): _stat("breakout", "BULL", 0.4),
        ("trend", "BEAR"): _stat("trend", "BEAR", 0.1),
        ("breakout", "BEAR"): _stat("breakout", "BEAR", 0.9),
    }
    selector = BundleSelector(SelectorInputs(pooled_oos_stats=stats))
    cands = [_sig("breakout"), _sig("trend")]

    bull = selector.rank_bundles("BULL", cands)
    assert [s.bundle for s in bull][0] == "trend"

    bear = selector.rank_bundles("BEAR", cands)
    assert [s.bundle for s in bear][0] == "breakout"


def test_min_n_floor_excludes_thin_bundles() -> None:
    stats = {
        ("trend", "BULL"): _stat("trend", "BULL", 2.0, n=5),  # below min_n
        ("breakout", "BULL"): _stat("breakout", "BULL", 0.8, n=50),
    }
    selector = BundleSelector(SelectorInputs(pooled_oos_stats=stats))
    ranked = selector.rank_bundles("BULL", [_sig("trend"), _sig("breakout")])
    assert [s.bundle for s in ranked] == ["breakout"]


@pytest.mark.hallmark
def test_default_composite_seed_top_quartile() -> None:
    """A11: Composite in top quartile -> seeded first."""
    stats = {
        ("composite", "BULL"): _stat("composite", "BULL", 1.4),
        ("trend", "BULL"): _stat("trend", "BULL", 1.5),
        ("breakout", "BULL"): _stat("breakout", "BULL", 0.5),
        ("vcp", "BULL"): _stat("vcp", "BULL", 0.3),
    }
    selector = BundleSelector(SelectorInputs(pooled_oos_stats=stats))
    cands = [_sig("trend"), _sig("breakout"), _sig("vcp"), _sig("composite")]
    ranked = selector.rank_bundles("BULL", cands)
    assert ranked[0].bundle == "composite"


@pytest.mark.hallmark
def test_default_seed_single_bundle_when_composite_mid_and_delta_decisive() -> None:
    """A11: Composite mid-pack + a single bundle with decisive Δ>=0.3 -> single bundle seeded."""
    stats = {
        ("composite", "BULL"): _stat("composite", "BULL", 0.4),
        ("trend", "BULL"): _stat("trend", "BULL", 1.5),
        ("breakout", "BULL"): _stat("breakout", "BULL", 0.5),
        ("vcp", "BULL"): _stat("vcp", "BULL", 0.45),
    }
    selector = BundleSelector(SelectorInputs(pooled_oos_stats=stats))
    cands = [_sig("trend"), _sig("breakout"), _sig("vcp"), _sig("composite")]
    ranked = selector.rank_bundles("BULL", cands)
    assert ranked[0].bundle == "trend"
