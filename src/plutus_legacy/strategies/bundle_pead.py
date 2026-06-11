# src/plutus/strategies/bundle_pead.py
"""
PEADBundle — Post-Earnings Announcement Drift (NSE-tuned).

Signal conditions:
  1. Earnings gap-up ≥ gap_min_pct on the gap bar with volume ≥ vol_min_ratio × SMA20.
  2. Within pullback_window bars after the gap, price pulls back to ≤ EMA10 × 1.02.
  3. Regime gate: skip when nifty_trend == "BEAR".
  4. Earnings season gate: only fire in Jan/Apr/Jul/Oct (configurable via earnings_months_only).

Stops/targets: ATR-anchored (1.5× stop, 2× T1, 3× T2).
Time-based exit: close after hold_days_max bars to cap holding period.
"""
import backtrader as bt
from plutus.strategies.base import BaseStrategy


class PEADBundle(BaseStrategy):
    """Bundle 7 — Post-Earnings Announcement Drift."""

    params = (
        ("gap_min_pct", 5.0),  # min gap-up % to qualify as earnings gap
        ("vol_min_ratio", 2.0),  # volume on gap day must be ≥ ratio × SMA20
        ("pullback_window", 5),  # bars after gap to look for EMA10 pullback entry
        ("hold_days_max", 15),  # time-based exit — max bars to hold
        (
            "earnings_months_only",
            True,
        ),  # gate to Jan/Apr/Jul/Oct (Indian earnings windows)
        ("sector_rs_top_n", 5),
    )

    def __init__(self):
        super().__init__()
        self.ema10 = bt.indicators.EMA(self.data.close, period=10)
        self.vol_ma = bt.indicators.SMA(self.data.volume, period=20)

        self._gap_bar = None  # bar-count when qualifying gap was first seen
        self._bars_held = 0

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _is_earnings_month(self) -> bool:
        """True when current bar falls in an Indian earnings window."""
        if not self.p.earnings_months_only:
            return True
        try:
            return self.data.datetime.date(0).month in (1, 4, 7, 10)
        except Exception:
            return True

    def _detect_gap(self) -> bool:
        """True if today opened ≥ gap_min_pct above yesterday's close with a volume surge."""
        if len(self.data) < 22:  # vol_ma safety guard
            return False
        close_prev = self.data.close[-1]
        open_now = self.data.open[0]
        if close_prev <= 0 or open_now <= 0:
            return False
        if (open_now - close_prev) / close_prev * 100 < self.p.gap_min_pct:
            return False
        if self.vol_ma[0] <= 0:
            return False
        return self.data.volume[0] >= self.p.vol_min_ratio * self.vol_ma[0]

    def has_long_signal(self) -> bool:
        """True while in an active PEAD setup window and price has pulled back to EMA10."""
        if self._gap_bar is None:
            return False
        bars_since_gap = len(self.data) - self._gap_bar
        if bars_since_gap < 1 or bars_since_gap > self.p.pullback_window:
            return False
        return self.data.close[0] <= self.ema10[0] * 1.02

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #

    def next(self):
        if self.order:
            return

        # Regime gate
        if self.p.nifty_trend == "BEAR":
            self._gap_bar = None
            return

        if not self.position:
            # Detect new earnings gap — only update if we're not already tracking one
            if self._is_earnings_month() and self._detect_gap():
                self._gap_bar = len(self.data)
                self._bars_held = 0

            if self.has_long_signal():
                entry = self.data.close[0]
                stop, t1, t2 = self.atr_stops_and_targets(entry)
                if stop >= entry or not self.rr_ok(entry, stop, t2):
                    return
                size = self.calc_position_size(entry, stop)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.stop_price = stop
                    self.t1_price = t1
                    self.t2_price = t2
                    self._gap_bar = None  # consumed — reset setup state
                    self._bars_held = 0
        else:
            self._bars_held += 1
            if (
                self.data.close[0] <= self.stop_price
                or (self.t2_price and self.data.close[0] >= self.t2_price)
                or (self.t1_price and self.data.close[0] >= self.t1_price)
                or self._bars_held >= self.p.hold_days_max
            ):
                self.order = self.close()
                self._bars_held = 0
