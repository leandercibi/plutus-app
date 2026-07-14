#!/usr/bin/env python3
"""Insert a mock second lot (SwingTrade + BUY Fill) for an existing OPEN symbol.

Local-only helper for visually testing multi-lot aggregation on the Positions
page. Idempotent-ish: appends a new SwingTrade + Fill row for the target symbol
so aggregation groups them into one row with N=lot_count lots. Re-run with a
different --symbol / --price / --days-ago to build up more lots.

Usage:
    cd backend
    python scripts/add_mock_second_lot.py                # picks first OPEN swing trade
    python scripts/add_mock_second_lot.py --symbol TITAN --price 4100 --qty 3 --days-ago 5
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, "src")

from sqlalchemy import select

from plutus.db.models import Fill, SwingSignal, SwingTrade
from plutus.db.session import session_scope


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--symbol", help="Symbol to add a second lot for (default: first OPEN swing trade)"
    )
    p.add_argument("--price", type=float, help="Fill price (default: original lot price * 1.03)")
    p.add_argument("--qty", type=int, default=5, help="Shares in the new lot (default 5)")
    p.add_argument(
        "--days-ago", type=int, default=7, help="How many days ago this lot opened (default 7)"
    )
    args = p.parse_args()

    with session_scope() as session:
        # Find an existing OPEN swing trade to model the new lot on.
        stmt = select(SwingTrade).where(SwingTrade.state.in_(["OPEN", "T1_HIT"]))
        if args.symbol:
            stmt = stmt.where(SwingTrade.symbol == args.symbol.upper())
        stmt = stmt.order_by(SwingTrade.opened_at.desc())
        base = session.execute(stmt).scalars().first()

        if base is None:
            print(f"❌ No OPEN swing trade found{' for ' + args.symbol if args.symbol else ''}.")
            print(
                "   Seed some positions first (e.g. run scripts/seed_demo_data.py or enter a signal in the UI)."
            )
            return 1

        # Reuse the base signal so the chart marker + risk_R make sense for the
        # new lot too. The new SwingTrade points to the same signal but is its
        # own row — the frontend aggregates by symbol|mode, so they collapse.
        base_signal = session.get(SwingSignal, base.signal_id)
        assert base_signal is not None

        base_fill = (
            session.execute(select(Fill).where(Fill.trade_id == base.id, Fill.side == "BUY"))
            .scalars()
            .first()
        )
        base_price = float(base_fill.price) if base_fill is not None else float(base_signal.entry)
        price = Decimal(str(args.price if args.price is not None else round(base_price * 1.03, 2)))

        opened_at = datetime.utcnow() - timedelta(days=args.days_ago)
        risk = float(base_signal.entry - base_signal.stop_loss)

        new_trade = SwingTrade(
            signal_id=base.signal_id,
            symbol=base.symbol,
            bundle=base.bundle,
            state="OPEN",
            opened_at=opened_at,
            qty=args.qty,
            risk_R=round(risk, 4) if risk > 0 else 1.0,
        )
        session.add(new_trade)
        session.flush()

        session.add(
            Fill(
                trade_id=new_trade.id,
                kind="MOCK",
                side="BUY",
                qty=args.qty,
                price=price,
                cost_inr=Decimal("0"),
                filled_at=opened_at,
            )
        )
        session.flush()

        print(
            f"✅ Added mock lot: {base.symbol} — {args.qty} shares @ ₹{price} "
            f"(opened {args.days_ago} days ago). trade_id={new_trade.id}"
        )
        print(f"   Refresh Positions page — {base.symbol} should now show a `N lots` badge.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
