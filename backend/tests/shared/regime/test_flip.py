from __future__ import annotations

from plutus.shared.regime.detector import RegimeVerdict
from plutus.shared.regime.flip import RegimeFlipDetector


def _verdict(label: str, breadth_confirmed: bool) -> RegimeVerdict:
    return RegimeVerdict(
        label=label,  # type: ignore[arg-type]
        confidence="high",
        reasons=[],
        breadth_confirmed=breadth_confirmed,
    )


def test_label_change_without_breadth_is_not_flip() -> None:
    detector = RegimeFlipDetector()
    prior = _verdict("BEAR", breadth_confirmed=True)
    current = _verdict("BULL", breadth_confirmed=False)
    assert detector.is_flip(prior, current) is False


def test_label_change_with_breadth_is_flip() -> None:
    detector = RegimeFlipDetector()
    prior = _verdict("BEAR", breadth_confirmed=True)
    current = _verdict("BULL", breadth_confirmed=True)
    assert detector.is_flip(prior, current) is True


def test_same_label_is_never_flip_even_with_breadth() -> None:
    detector = RegimeFlipDetector()
    prior = _verdict("BULL", breadth_confirmed=True)
    current = _verdict("BULL", breadth_confirmed=True)
    assert detector.is_flip(prior, current) is False
