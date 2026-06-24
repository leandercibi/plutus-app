from __future__ import annotations

from plutus.shared.calibration.multiple_testing import (
    benjamini_hochberg,
    family_size,
)


def test_benjamini_hochberg_classic_fixture() -> None:
    # Benjamini-Hochberg 1995 style: clear signals at low p, noise at high p.
    p = [0.001, 0.008, 0.039, 0.041, 0.9, 0.95]
    mask = benjamini_hochberg(p, q=0.05)
    # the three smallest pass BH at q=0.05; the large noise ones do not
    assert mask[0] is True
    assert mask[1] is True
    assert mask[4] is False
    assert mask[5] is False


def test_empty_returns_empty() -> None:
    assert benjamini_hochberg([]) == []


def test_all_large_p_none_pass() -> None:
    assert benjamini_hochberg([0.9, 0.8, 0.95], q=0.10) == [False, False, False]


def test_family_size_multiplies() -> None:
    assert family_size(buckets=5, bundles=4, regimes=3) == 60
