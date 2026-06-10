# tests/test_bundle_hardening/test_base.py
"""Tests for BaseStrategy ATR helpers and R:R gate."""
from tests.test_bundle_hardening.conftest import run_strategy, make_bull_df
from plutus.strategies.base import BaseStrategy, MIN_RR


class _AlwaysBuyStub(BaseStrategy):
    """Buys once on bar 60 using ATR helpers, exits at T1."""
    def has_long_signal(self):
        return len(self.data) == 60

    def next(self):
        if self.order:
            return
        if not self.position and self.has_long_signal():
            entry = self.data.close[0]
            stop, t1, t2 = self.atr_stops_and_targets(entry)
            if self.rr_ok(entry, stop, t2):
                size = self.calc_position_size(entry, stop)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.stop_price = stop
                    self.t1_price   = t1
                    self.t2_price   = t2
        elif self.position and self.t1_price and self.data.close[0] >= self.t1_price:
            self.order = self.close()


def _strat():
    return run_strategy(make_bull_df(), _AlwaysBuyStub)


def test_min_rr_constant():
    assert MIN_RR == 2.0


def test_rr_ok_rejects_below_floor():
    strat = _strat()
    assert not strat.rr_ok(100.0, 98.0, 103.0)   # R:R=1.5 → False


def test_rr_ok_accepts_at_floor():
    strat = _strat()
    assert strat.rr_ok(100.0, 98.0, 104.0)        # R:R=2.0 → True


def test_rr_ok_accepts_above_floor():
    strat = _strat()
    assert strat.rr_ok(100.0, 98.0, 107.0)        # R:R=3.5 → True


def test_rr_ok_zero_risk():
    strat = _strat()
    assert not strat.rr_ok(100.0, 100.0, 110.0)   # risk=0 → False


def test_t1_t2_relationship():
    strat = _strat()
    stop, t1, t2 = strat.atr_stops_and_targets(500.0)
    assert t2 > t1 > 500.0 > stop


def test_stop_distance_equals_mult_times_atr():
    strat = _strat()
    entry = 1000.0
    stop, _, _ = strat.atr_stops_and_targets(entry)
    atr_val = strat.atr[0]
    assert abs((entry - stop) - strat.p.atr_stop_mult * atr_val) < 1e-6


def test_t1_distance_equals_mult_times_atr():
    strat = _strat()
    entry = 1000.0
    _, t1, _ = strat.atr_stops_and_targets(entry)
    atr_val = strat.atr[0]
    assert abs((t1 - entry) - strat.p.atr_t1_mult * atr_val) < 1e-6


def test_default_rr_with_atr_params_passes_floor():
    """Default atr_t2_mult=3.0 / atr_stop_mult=1.5 = R:R 2.0 — meets floor."""
    strat = _strat()
    entry = 1000.0
    stop, _, t2 = strat.atr_stops_and_targets(entry)
    assert strat.rr_ok(entry, stop, t2)


def test_calc_position_size_zero_risk():
    strat = _strat()
    assert strat.calc_position_size(100.0, 100.0) == 0


def test_calc_position_size_valid():
    strat = _strat()
    size = strat.calc_position_size(100.0, 95.0)
    assert size > 0
