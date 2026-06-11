# src/plutus/backtesting/paper_trader.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from plutus.config import settings
from plutus.data.ohlcv import fetch_live_price
from plutus.db.models import (
    MockPortfolio,
    PaperTrade,
    Recommendation,
    TradeDirection,
    TradeStatus,
)
from plutus.db.session import SessionLocal


@dataclass
class BuyResult:
    """Returned by PaperTrader.buy() — trade is always recorded if cash sufficient."""

    trade_id: int
    capital_used: float
    risk_pct: Optional[float]  # None when no recommendation/stop linked
    warnings: List[str]  # human-readable advisory strings; may be empty


class PaperTrader:
    """Per-portfolio paper trading engine."""

    def __init__(self, portfolio_name: str):
        self.portfolio_name = portfolio_name
        self._ensure_portfolio_exists()

    # ------------------------------------------------------------------ #
    # Portfolio lifecycle
    # ------------------------------------------------------------------ #
    def _ensure_portfolio_exists(self) -> None:
        with SessionLocal() as db:
            portfolio = (
                db.query(MockPortfolio)
                .filter(MockPortfolio.name == self.portfolio_name)
                .first()
            )
            if not portfolio:
                raise ValueError(
                    f"Portfolio '{self.portfolio_name}' not found. Create it first."
                )

    @staticmethod
    def create_portfolio(
        name: str, initial_capital: float, notes: str = ""
    ) -> MockPortfolio:
        with SessionLocal() as db:
            existing = (
                db.query(MockPortfolio).filter(MockPortfolio.name == name).first()
            )
            if existing:
                raise ValueError(f"Portfolio '{name}' already exists.")
            portfolio = MockPortfolio(
                name=name,
                initial_capital=initial_capital,
                notes=notes,
            )
            db.add(portfolio)
            db.commit()
            db.refresh(portfolio)
            return portfolio

    # ------------------------------------------------------------------ #
    # Buy
    # ------------------------------------------------------------------ #
    def buy(
        self,
        symbol: str,
        price: float,
        shares: int,
        strategy_used: str = "",
        recommendation_id: Optional[int] = None,
    ) -> BuyResult:
        """Record a paper buy.

        Hard reject (raises ValueError):
            - cash insufficient for `price * shares`
            - open positions would exceed `MAX_OPEN_POSITIONS_HARD`

        Soft warnings (returned in BuyResult.warnings, trade is still recorded):
            - open positions after this trade exceeds `MAX_OPEN_POSITIONS_ADVISORY`
            - trade risk (using rec.stop_loss) exceeds `RISK_PCT_PER_TRADE`
              of initial_capital
        """
        if shares <= 0:
            raise ValueError("shares must be > 0")
        if price <= 0:
            raise ValueError("price must be > 0")

        capital_used = price * shares
        warnings: List[str] = []
        risk_pct: Optional[float] = None

        with SessionLocal() as db:
            portfolio = (
                db.query(MockPortfolio)
                .filter(MockPortfolio.name == self.portfolio_name)
                .first()
            )

            # ---- HARD REJECT: cash --------------------------------------
            if capital_used > portfolio.current_cash:
                raise ValueError(
                    f"Insufficient cash: need ₹{capital_used:,.0f}, "
                    f"have ₹{portfolio.current_cash:,.0f}"
                )

            # ---- HARD REJECT: position hard cap -------------------------
            open_count = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.portfolio_id == portfolio.id,
                    PaperTrade.status == TradeStatus.OPEN,
                )
                .count()
            )
            if open_count + 1 > settings.MAX_OPEN_POSITIONS_HARD:
                raise ValueError(
                    f"Hard cap reached: cannot exceed "
                    f"{settings.MAX_OPEN_POSITIONS_HARD} open positions"
                )

            # ---- SOFT WARNING: positions advisory -----------------------
            if open_count + 1 > settings.MAX_OPEN_POSITIONS_ADVISORY:
                warnings.append(
                    f"Open positions after this trade: {open_count + 1} "
                    f"(advisory limit {settings.MAX_OPEN_POSITIONS_ADVISORY})"
                )

            # ---- SOFT WARNING: per-trade risk vs recommendation stop ----
            if recommendation_id is not None:
                rec = db.query(Recommendation).get(recommendation_id)
                if rec and rec.stop_loss:
                    per_share_risk = max(price - float(rec.stop_loss), 0.0)
                    trade_risk = per_share_risk * shares
                    if portfolio.initial_capital > 0:
                        risk_pct = round(
                            trade_risk / float(portfolio.initial_capital) * 100, 2
                        )
                        if risk_pct > settings.RISK_PCT_PER_TRADE:
                            warnings.append(
                                f"Risk on this trade is {risk_pct:.2f}% of "
                                f"initial capital (limit "
                                f"{settings.RISK_PCT_PER_TRADE:.1f}%)"
                            )

            # ---- record trade -------------------------------------------
            trade = PaperTrade(
                portfolio_id=portfolio.id,
                symbol=symbol.upper(),
                direction=TradeDirection.LONG,
                entry_price=price,
                entry_date=datetime.utcnow(),
                shares=shares,
                capital_used=capital_used,
                strategy_used=strategy_used,
                status=TradeStatus.OPEN,
                linked_recommendation_id=recommendation_id,
            )
            db.add(trade)
            db.commit()
            db.refresh(trade)

            if warnings:
                warnings.append(f"trade_id={trade.id}")

            return BuyResult(
                trade_id=trade.id,
                capital_used=round(capital_used, 2),
                risk_pct=risk_pct,
                warnings=warnings,
            )

    # ------------------------------------------------------------------ #
    # Sell
    # ------------------------------------------------------------------ #
    def sell(self, symbol: str, price: float, shares: int) -> Dict:
        """Close (or partially close) the oldest open position for `symbol`.

        Returns: {trade_id, shares_closed, realised_pnl, realised_pnl_pct,
                  remaining_shares}
        """
        if shares <= 0:
            raise ValueError("shares must be > 0")
        if price <= 0:
            raise ValueError("price must be > 0")

        with SessionLocal() as db:
            portfolio = (
                db.query(MockPortfolio)
                .filter(MockPortfolio.name == self.portfolio_name)
                .first()
            )
            trade = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.portfolio_id == portfolio.id,
                    PaperTrade.symbol == symbol.upper(),
                    PaperTrade.status == TradeStatus.OPEN,
                )
                .order_by(PaperTrade.entry_date.asc())
                .first()
            )
            if not trade:
                raise ValueError(
                    f"No open position for {symbol} in portfolio "
                    f"'{self.portfolio_name}'"
                )

            close_shares = min(shares, trade.shares)
            entry = float(trade.entry_price)
            realised_pnl = (price - entry) * close_shares
            realised_pnl_pct = (price - entry) / entry * 100.0
            proceeds = price * close_shares

            remaining = trade.shares - close_shares
            if remaining == 0:
                trade.exit_price = price
                trade.exit_date = datetime.utcnow()
                trade.realised_pnl = round(realised_pnl, 2)
                trade.realised_pnl_pct = round(realised_pnl_pct, 2)
                trade.status = TradeStatus.CLOSED
            else:
                # Partial close: split into a closed sibling and shrink the open trade.
                closed_sibling = PaperTrade(
                    portfolio_id=portfolio.id,
                    symbol=trade.symbol,
                    direction=trade.direction,
                    entry_price=entry,
                    entry_date=trade.entry_date,
                    shares=close_shares,
                    capital_used=entry * close_shares,
                    strategy_used=trade.strategy_used,
                    linked_recommendation_id=trade.linked_recommendation_id,
                    status=TradeStatus.CLOSED,
                    exit_price=price,
                    exit_date=datetime.utcnow(),
                    realised_pnl=round(realised_pnl, 2),
                    realised_pnl_pct=round(realised_pnl_pct, 2),
                )
                db.add(closed_sibling)
                trade.shares = remaining
                trade.capital_used = float(trade.capital_used) - (entry * close_shares)

            db.commit()

            return {
                "trade_id": trade.id,
                "shares_closed": close_shares,
                "realised_pnl": round(realised_pnl, 2),
                "realised_pnl_pct": round(realised_pnl_pct, 2),
                "remaining_shares": remaining,
            }

    # ------------------------------------------------------------------ #
    # Read APIs
    # ------------------------------------------------------------------ #
    def get_positions(self) -> List[Dict]:
        """Open positions for this portfolio with mark-to-market unrealised P&L."""
        out: List[Dict] = []
        with SessionLocal() as db:
            portfolio = (
                db.query(MockPortfolio)
                .filter(MockPortfolio.name == self.portfolio_name)
                .first()
            )
            open_trades = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.portfolio_id == portfolio.id,
                    PaperTrade.status == TradeStatus.OPEN,
                )
                .order_by(PaperTrade.entry_date.asc())
                .all()
            )
            for t in open_trades:
                try:
                    ltp = fetch_live_price(t.symbol)
                    unreal = (ltp - float(t.entry_price)) * t.shares
                    unreal_pct = (
                        (ltp - float(t.entry_price)) / float(t.entry_price) * 100
                    )
                except Exception:
                    ltp = float(t.entry_price)
                    unreal = 0.0
                    unreal_pct = 0.0
                out.append(
                    {
                        "trade_id": t.id,
                        "symbol": t.symbol,
                        "shares": t.shares,
                        "entry_price": float(t.entry_price),
                        "entry_date": t.entry_date.isoformat(),
                        "current_price": round(ltp, 2),
                        "unrealised_pnl": round(unreal, 2),
                        "unrealised_pnl_pct": round(unreal_pct, 2),
                        "capital_used": float(t.capital_used),
                        "strategy_used": t.strategy_used or "",
                        "linked_recommendation_id": t.linked_recommendation_id,
                    }
                )
        return out

    def get_summary(self) -> Dict:
        """Portfolio-level snapshot."""
        with SessionLocal() as db:
            portfolio = (
                db.query(MockPortfolio)
                .filter(MockPortfolio.name == self.portfolio_name)
                .first()
            )
            all_trades = (
                db.query(PaperTrade)
                .filter(PaperTrade.portfolio_id == portfolio.id)
                .all()
            )
            closed = [t for t in all_trades if t.status == TradeStatus.CLOSED]
            open_trades = [t for t in all_trades if t.status == TradeStatus.OPEN]

            realised_pnl = sum(float(t.realised_pnl or 0) for t in closed)
            wins = [t for t in closed if float(t.realised_pnl or 0) > 0]
            win_rate = (len(wins) / len(closed) * 100.0) if closed else 0.0

            unrealised_pnl = 0.0
            mtm_value = 0.0
            for t in open_trades:
                try:
                    ltp = fetch_live_price(t.symbol)
                except Exception:
                    ltp = float(t.entry_price)
                unrealised_pnl += (ltp - float(t.entry_price)) * t.shares
                mtm_value += ltp * t.shares

            open_capital = sum(float(t.capital_used or 0) for t in open_trades)
            closed_pnl = sum(float(t.realised_pnl or 0) for t in closed)
            cash = float(portfolio.initial_capital) - open_capital + closed_pnl
            current_value = cash + mtm_value

            return {
                "initial_capital": float(portfolio.initial_capital),
                "current_cash": round(cash, 2),
                "current_value": round(current_value, 2),
                "realised_pnl": round(realised_pnl, 2),
                "unrealised_pnl": round(unrealised_pnl, 2),
                "win_rate": round(win_rate, 1),
                "open_count": len(open_trades),
                "closed_count": len(closed),
            }


def list_portfolios() -> List[Dict]:
    """Lightweight listing for the dashboard / Telegram `/portfolios`."""
    out: List[Dict] = []
    with SessionLocal() as db:
        portfolios = db.query(MockPortfolio).all()
        for p in portfolios:
            closed = [t for t in p.trades if t.status == TradeStatus.CLOSED]
            open_trades = [t for t in p.trades if t.status == TradeStatus.OPEN]
            realised = sum(float(t.realised_pnl or 0) for t in closed)
            wins = [t for t in closed if float(t.realised_pnl or 0) > 0]
            win_rate = (len(wins) / len(closed) * 100.0) if closed else 0.0
            out.append(
                {
                    "name": p.name,
                    "initial_capital": float(p.initial_capital),
                    "current_cash": round(float(p.current_cash), 2),
                    "realised_pnl": round(realised, 2),
                    "win_rate": round(win_rate, 1),
                    "open_count": len(open_trades),
                    "closed_count": len(closed),
                    "created_at": p.created_at.strftime("%Y-%m-%d"),
                }
            )
    return out
