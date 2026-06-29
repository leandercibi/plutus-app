from __future__ import annotations

from plutus.shared.calibration.sprt import SPRT


def _sprt() -> SPRT:
    # H0: 0R (no edge); H1: +0.5R edge
    return SPRT(alpha=0.05, beta=0.20, h0_expectancy=0.0, h1_expectancy=0.5)


def test_stream_of_wins_accepts_h1() -> None:
    sprt = _sprt()
    state = sprt.initial()
    for _ in range(100):
        state = sprt.update(state, 1.0)
        if state.decision == "accept_H1":
            break
    assert state.decision == "accept_H1"


def test_stream_of_losses_accepts_h0() -> None:
    sprt = _sprt()
    state = sprt.initial()
    for _ in range(100):
        state = sprt.update(state, -1.0)
        if state.decision == "accept_H0":
            break
    assert state.decision == "accept_H0"


def test_mixed_stays_continue() -> None:
    sprt = _sprt()
    state = sprt.initial()
    for i in range(10):
        state = sprt.update(state, 0.25 if i % 2 == 0 else -0.25)
    assert state.decision == "continue"
