# src/plutus/strategies/base.py
import backtrader as bt

# R:R floor enforced by every bundle — setups below this are skipped.
MIN_RR = 2.0


class BaseStrategy(bt.Strategy):
    """
    Shared base for all 5 bundles.

    Subclasses MUST override:
        has_long_signal(self) -> bool      — pure indicator read; no order/position state
        next(self)                         — entry / exit plumbing using has_long_signal()

    ATR-based stop/target convention (all bundles):
        stop  = entry - atr_stop_mult  × ATR(14)   (default 1.5×)
        T1    = entry + atr_t1_mult    × ATR(14)   (default 2×)
        T2    = entry + atr_t2_mult    × ATR(14)   (default 3×)

    Regime params (optional — set at run-time; None = no filter):
        nifty_trend     : "BULL" | "BEAR" | "SIDEWAYS" | None
        sector_rs_rank  : int rank (1 = strongest) | None
    """
    params = (
        ("risk_pct",        5.0),   # % of cash to risk per trade
        ("atr_stop_mult",   1.5),   # stop = entry - mult × ATR(14)
        ("atr_t1_mult",     2.0),   # T1   = entry + mult × ATR(14)
        ("atr_t2_mult",     3.0),   # T2   = entry + mult × ATR(14)
        ("min_rr",          2.0),   # minimum R:R; setups below this are skipped
        ("nifty_trend",     None),  # optional regime gate
        ("sector_rs_rank",  None),  # optional sector rank gate (1 = top)
    )

    def __init__(self):
        self.order = None
        self.entry_price = None
        self.stop_price = None
        self.t1_price = None
        self.t2_price = None
        self.target_price = None    # backward-compat alias = t1_price
        self.trade_log = []

        self.atr = bt.indicators.ATR(self.data, period=14)

    # ------------------------------------------------------------------ #
    # ATR helpers
    # ------------------------------------------------------------------ #
    def atr_stops_and_targets(self, entry: float) -> tuple[float, float, float]:
        """Return (stop, t1, t2) anchored to current ATR."""
        atr_val = self.atr[0]
        stop = entry - self.p.atr_stop_mult * atr_val
        t1   = entry + self.p.atr_t1_mult   * atr_val
        t2   = entry + self.p.atr_t2_mult   * atr_val
        return stop, t1, t2

    def rr_ok(self, entry: float, stop: float, t2: float) -> bool:
        """True when setup's R:R (using T2) meets the floor.

        With defaults (stop=1.5×ATR, T2=3×ATR): R:R = 3/1.5 = 2.0 — exactly
        meets the floor. T1 alone (2×ATR / 1.5×ATR = 1.33) would always fail.
        """
        risk = entry - stop
        if risk <= 0:
            return False
        return (t2 - entry) / risk >= self.p.min_rr

    # ------------------------------------------------------------------ #
    # Signal API
    # ------------------------------------------------------------------ #
    def has_long_signal(self) -> bool:
        """Return True if indicator conditions hold. Bundles 1–4 override."""
        return False

    # ------------------------------------------------------------------ #
    # Sizing
    # ------------------------------------------------------------------ #
    def calc_position_size(self, entry: float, stop: float) -> int:
        """Risk-based position sizing.

        Risk per trade = (risk_pct/100) × current_cash.
        Hard cap: never deploy more than 25% of cash on a single trade.
        """
        per_share_risk = abs(entry - stop)
        if per_share_risk <= 0 or entry <= 0:
            return 0
        cash = self.broker.getcash()
        risk_budget = cash * (self.p.risk_pct / 100.0)
        shares_by_risk = int(risk_budget // per_share_risk)
        shares_by_cap  = int((cash * 0.25) // entry)
        return max(0, min(shares_by_risk, shares_by_cap))

    # ------------------------------------------------------------------ #
    # Order / trade plumbing
    # ------------------------------------------------------------------ #
    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.entry_price = order.executed.price
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        size = trade.size or 1
        self.trade_log.append({
            "pnl":      round(trade.pnl, 2),
            "pnl_pct":  round((trade.pnl / (trade.price * abs(size))) * 100, 2),
            "entry":    round(trade.price, 2),
            "exit":     round(trade.price + trade.pnl / size, 2),
            "size":     size,
            "bars_held": trade.barlen,
        })
