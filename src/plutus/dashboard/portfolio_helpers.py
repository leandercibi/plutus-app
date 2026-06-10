# src/plutus/dashboard/portfolio_helpers.py
"""Pure utility functions for the Portfolio tab — no Streamlit, no module-level DB calls."""
from __future__ import annotations

from typing import Any, Dict, List


def get_trade_history(portfolio_name: str) -> List[Dict[str, Any]]:
    """Return closed trades for *portfolio_name* as plain dicts, or [] if not found."""
    from plutus.db.session import SessionLocal
    from plutus.db.models import MockPortfolio, PaperTrade, TradeStatus

    with SessionLocal() as db:
        p = db.query(MockPortfolio).filter(MockPortfolio.name == portfolio_name).first()
        if not p:
            return []
        trades = (
            db.query(PaperTrade)
            .filter(PaperTrade.portfolio_id == p.id, PaperTrade.status == TradeStatus.CLOSED)
            .order_by(PaperTrade.exit_date.asc())
            .all()
        )
    return [
        {
            "symbol": t.symbol,
            "side": t.direction.value,
            "entry_price": t.entry_price,
            "entry_date": t.entry_date,
            "exit_price": t.exit_price,
            "exit_date": t.exit_date,
            "shares": t.shares,
            "realised_pnl": t.realised_pnl,
            "realised_pnl_pct": t.realised_pnl_pct,
            "exit_reason": t.exit_reason.value if t.exit_reason else None,
        }
        for t in trades
    ]
