# src/plutus/strategies/base.py
import backtrader as bt


class BaseStrategy(bt.Strategy):
    """
    Shared base for all 5 bundles.

    Subclasses MUST override:
        has_long_signal(self) -> bool      — pure indicator read; no order/position state
        next(self)                         — entry / exit plumbing using has_long_signal()
    """
    params = (
        ("risk_pct", 5.0),     # % of cash to risk per trade
        ("rr_ratio", 2.0),     # reward-to-risk multiple used to derive target from stop
    )

    def __init__(self):
        self.order = None
        self.entry_price = None
        self.stop_price = None
        self.target_price = None
        self.trade_log = []

        # Indicators that every bundle relies on. Subclass __init__ adds its own.
        self.atr = bt.indicators.ATR(self.data, period=14)

    # ------------------------------------------------------------------ #
    # Signal API
    # ------------------------------------------------------------------ #
    def has_long_signal(self) -> bool:
        """Return True if conditions for a long entry hold on the current bar.

        Default is False; bundles 1–4 override. Composite aggregates the four.
        """
        return False

    # ------------------------------------------------------------------ #
    # Sizing
    # ------------------------------------------------------------------ #
    def calc_position_size(self, entry: float, stop: float) -> int:
        """Risk-based position sizing.

        Risk per trade = (risk_pct/100) × current_cash.
        Shares = floor(risk_per_trade / per_share_risk).
        Hard cap: never deploy more than 25% of cash on a single trade.
        """
        per_share_risk = abs(entry - stop)
        if per_share_risk <= 0 or entry <= 0:
            return 0
        cash = self.broker.getcash()
        risk_budget = cash * (self.p.risk_pct / 100.0)
        shares_by_risk = int(risk_budget // per_share_risk)
        shares_by_cap = int((cash * 0.25) // entry)
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
            "pnl": round(trade.pnl, 2),
            "pnl_pct": round((trade.pnl / (trade.price * abs(size))) * 100, 2),
            "entry": round(trade.price, 2),
            "exit": round(trade.price + trade.pnl / size, 2),
            "size": size,
            "bars_held": trade.barlen,
        })
