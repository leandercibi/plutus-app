from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SPRTState:
    llr: float
    decision: str  # "accept_H0" | "accept_H1" | "continue"


class SPRT:
    """A14 — sequential probability ratio test on per-trade R outcomes.

    H0: bundle expectancy ~ h0_expectancy (do nothing).
    H1: bundle expectancy ~ h1_expectancy (act). A normal-likelihood SPRT on R.
    """

    def __init__(
        self,
        alpha: float,
        beta: float,
        h0_expectancy: float,
        h1_expectancy: float,
        sigma: float = 1.0,
    ) -> None:
        import math

        self._A = math.log((1 - beta) / alpha)
        self._B = math.log(beta / (1 - alpha))
        self._h0 = h0_expectancy
        self._h1 = h1_expectancy
        self._sigma2 = sigma * sigma

    def initial(self) -> SPRTState:
        return SPRTState(llr=0.0, decision="continue")

    def update(self, prior_state: SPRTState, new_outcome_R: float) -> SPRTState:
        # log-likelihood increment for a normal with known variance
        increment = (
            (self._h1 - self._h0)
            * (new_outcome_R - (self._h1 + self._h0) / 2.0)
            / self._sigma2
        )
        llr = prior_state.llr + increment
        if llr >= self._A:
            decision = "accept_H1"
        elif llr <= self._B:
            decision = "accept_H0"
        else:
            decision = "continue"
        return SPRTState(llr=llr, decision=decision)
